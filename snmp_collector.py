#!/usr/bin/env python3
"""
SNMP Collector for APC PDU Power Monitoring
Collects power consumption data from APC PDUs via SNMPv2c/SNMPv3
"""

import time
import logging
from datetime import datetime, timedelta
from easysnmp import Session
from config import PDUS, SNMP_PORT, SNMP_TIMEOUT, SNMP_RETRIES, POWER_OID
from models import db, PDU, PowerReading
import traceback

# Primary OIDs for amperage readings (much more stable than power)
# Based on your SNMP walk showing L1 phase load at 1.9A and 2.5A
L1_PHASE_CURRENT_OID = "1.3.6.1.4.1.318.1.1.12.2.3.1.1.2.1"  # L1 phase current in 0.1A units (most stable!)
L2_PHASE_CURRENT_OID = "1.3.6.1.4.1.318.1.1.12.2.3.1.1.1.1"  # L2 phase current in 0.1A units
L3_PHASE_CURRENT_OID = "1.3.6.1.4.1.318.1.1.12.2.3.1.1.3.1"  # L3 phase current in 0.1A units

# Total PDU current OIDs (if available)
TOTAL_CURRENT_OIDS = [
    "1.3.6.1.4.1.318.1.1.12.2.3.1.1.4.1",  # Phase 4 current in 0.1A units
    "1.3.6.1.4.1.318.1.1.12.2.3.1.1.5.1",  # Phase 5 current in 0.1A units
]

# Fallback power OIDs (if amperage fails)
FALLBACK_POWER_OIDS = [
    "1.3.6.1.4.1.318.1.1.12.1.16.0",  # Total PDU power in watts (working!)
    "1.3.6.1.4.1.318.1.1.4.4.2.1.4.0",  # Total PDU power (from SNMP walk)
]

# Fallback power OIDs (if amperage fails)
FALLBACK_POWER_OIDS = [
    "1.3.6.1.4.1.318.1.1.12.1.16.0",  # Total PDU power in watts (working!)
    "1.3.6.1.4.1.318.1.1.4.4.2.1.4.0",  # Total PDU power (from SNMP walk)
]

# PDU voltage configuration (adjust based on your setup)
PDU_VOLTAGE = 240  # Volts - UK voltage
PDU_POWER_FACTOR = 0.95  # Typical power factor for IT equipment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdu_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PDUCollector:
    def __init__(self):
        # Store last known good readings to handle flickering
        self.last_readings = {}
    
    def get_power_reading(self, pdu_config):
        """Get power reading from a single PDU with anti-flickering logic"""
        try:
            # Try SNMPv2c first (since that's what works for the user)
            reading_value = self._try_snmp_v2c(pdu_config)
            
            if reading_value is None:
                # Fallback to SNMPv3 if v2c fails
                reading_value = self._try_snmp_v3(pdu_config)
            
            # Apply anti-flickering logic
            if reading_value is not None and reading_value >= 0:
                reading_value = self._apply_anti_flickering(pdu_config['name'], reading_value)
            
            # Check if we have valid data after anti-flickering
            if reading_value is not None and reading_value > 0:
                # Convert current to power if we got a current reading
                if reading_value < 100:  # Likely current in amps (not power in watts)
                    current_amps = reading_value
                    power_watts = current_amps * PDU_VOLTAGE * PDU_POWER_FACTOR
                    
                    # Validate the calculated power is reasonable for a 16A circuit
                    max_power_16a = 16 * PDU_VOLTAGE * PDU_POWER_FACTOR  # ~3,648W for 16A at 240V
                    if power_watts > max_power_16a:
                        logger.error(f"🚨 Calculated power exceeds 16A circuit limit: {power_watts:.1f}W from {current_amps:.1f}A (max: {max_power_16a:.1f}W) - possible calculation error")
                        return None
                    
                    logger.info(f"💡 Current reading: {current_amps:.1f}A → Power: {power_watts:.1f}W ({power_watts/1000.0:.3f}kW)")
                else:
                    # Direct power reading
                    power_watts = reading_value
                    
                    # Validate the power reading is reasonable for a 16A circuit
                    max_power_16a = 16 * PDU_VOLTAGE * PDU_POWER_FACTOR  # ~3,648W for 16A at 240V
                    if power_watts > max_power_16a:
                        logger.error(f"🚨 Power reading exceeds 16A circuit limit: {power_watts:.1f}W (max: {max_power_16a:.1f}W) - possible sensor error")
                        return None
                    
                    logger.info(f"💡 Power reading: {power_watts}W ({power_watts/1000.0:.3f}kW)")
                
                power_kw = power_watts / 1000.0
                return {
                    'power_watts': power_watts,
                    'power_kw': power_kw,
                    'current_amps': current_amps if reading_value < 100 else None
                }
            elif reading_value == 0:
                logger.warning(f"⚠️ Reading is 0 - this might indicate a flicker or no load")
                return None
            else:
                logger.warning(f"⚠️ No valid data found from any OID")
                return None
                
        except Exception as e:
            logger.error(f"Error collecting from {pdu_config['name']}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def _try_snmp_v2c(self, pdu_config):
        """Try SNMPv2c first (most reliable for this PDU)"""
        try:
            # Try the L1 phase current OID first (highest priority - most stable!)
            session = Session(
                hostname=pdu_config['ip'],
                version=2,
                community='public',
                timeout=SNMP_TIMEOUT,
                retries=SNMP_RETRIES
            )
            
            logger.info(f"🔍 Trying SNMPv2c with L1 phase current OID for {pdu_config['name']}...")
            
            # Try the L1 phase current OID first (highest priority - most stable!)
            try:
                result = session.get(L1_PHASE_CURRENT_OID)
                if result and result.value:
                    value = int(result.value)
                    logger.info(f"🔍 Raw SNMP value from L1 phase current OID: {value} (type: {type(value)})")
                    if value > 0:  # Valid current reading (in 0.1A units)
                        current_amps = value / 10.0  # Convert from 0.1A units to amps
                        
                        # Validate current doesn't exceed 16A circuit limit
                        if current_amps > 16:
                            logger.error(f"🚨 Current reading exceeds 16A circuit limit: {current_amps:.1f}A (raw: {value}) - possible sensor error")
                            return None
                        
                        logger.info(f"✅ Found L1 phase current with SNMPv2c: {current_amps:.1f}A (gauge: {value})")
                        return current_amps
            except Exception as e:
                logger.debug(f"L1 phase current OID failed with SNMPv2c: {str(e)}")
            
            # Try other phase current OIDs with SNMPv2c
            for oid in [L2_PHASE_CURRENT_OID, L3_PHASE_CURRENT_OID]:
                try:
                    result = session.get(oid)
                    if result and result.value:
                        value = int(result.value)
                        if value > 0:  # Valid current reading (in 0.1A units)
                            current_amps = value / 10.0  # Convert from 0.1A units to amps
                            
                            # Validate current doesn't exceed 16A circuit limit
                            if current_amps > 16:
                                logger.error(f"🚨 Current reading exceeds 16A circuit limit: {current_amps:.1f}A (raw: {value}) - possible sensor error")
                                continue
                            
                            logger.info(f"✅ Found phase current with SNMPv2c: {current_amps:.1f}A (gauge: {value})")
                            return current_amps
                except Exception as e:
                    logger.debug(f"Phase current OID {oid} failed with SNMPv2c: {str(e)}")
                    continue
            
            # Fallback to power OIDs if current fails
            logger.info(f"Current OIDs failed, trying power OIDs as fallback...")
            for oid in FALLBACK_POWER_OIDS:
                try:
                    result = session.get(oid)
                    if result and result.value:
                        value = int(result.value)
                        logger.info(f"🔍 Raw SNMP value from power OID {oid}: {value} (type: {type(value)})")
                        if value > 0:  # Valid power reading
                            logger.info(f"✅ Found power with SNMPv2c at {oid}: {value}W")
                            return value
                except Exception as e:
                    logger.debug(f"Power OID {oid} failed with SNMPv2c: {str(e)}")
                    continue
            
            return None
            
        except Exception as e:
            logger.debug(f"SNMPv2c failed: {str(e)}")
            return None
    
    def _try_snmp_v3(self, pdu_config):
        """Fallback to SNMPv3 if v2c fails"""
        try:
            # Create SNMP session with easysnmp
            session = Session(
                hostname=pdu_config['ip'],
                version=3,
                security_level='authPriv',
                security_username=pdu_config['username'],
                auth_password=pdu_config['auth_passphrase'],
                privacy_password=pdu_config['privacy_passphrase'],
                timeout=SNMP_TIMEOUT,
                retries=SNMP_RETRIES
            )
            
            logger.info(f"🔍 SNMPv2c failed, trying SNMPv3 for {pdu_config['name']}...")
            
            # Try the L1 phase current OID first
            try:
                result = session.get(L1_PHASE_CURRENT_OID)
                if result and result.value:
                    value = int(result.value)
                    if value > 0:  # Valid current reading (in 0.1A units)
                        current_amps = value / 10.0  # Convert from 0.1A units to amps
                        logger.info(f"✅ Found L1 phase current with SNMPv3: {current_amps:.1f}A (gauge: {value})")
                        return current_amps
            except Exception as e:
                logger.debug(f"L1 phase current OID failed with SNMPv3: {str(e)}")
            
            # Try other phase current OIDs
            for oid in [L2_PHASE_CURRENT_OID, L3_PHASE_CURRENT_OID]:
                try:
                    result = session.get(oid)
                    if result and result.value:
                        value = int(result.value)
                        if value > 0:  # Valid current reading (in 0.1A units)
                            current_amps = value / 10.0  # Convert from 0.1A units to amps
                            logger.info(f"✅ Found phase current with SNMPv3: {current_amps:.1f}A (gauge: {value})")
                            return current_amps
                except Exception as e:
                    logger.debug(f"Phase current OID {oid} failed with SNMPv3: {str(e)}")
                    continue
            
            # Fallback to power OIDs if current fails
            logger.info(f"Current OIDs failed, trying power OIDs as fallback...")
            for oid in FALLBACK_POWER_OIDS:
                try:
                    result = session.get(oid)
                    if result and result.value:
                        value = int(result.value)
                        if value > 0:  # Valid power reading
                            logger.info(f"✅ Found power with SNMPv3 at {oid}: {value}W")
                            return value
                except Exception as e:
                    logger.debug(f"Power OID {oid} failed with SNMPv3: {str(e)}")
                    continue
            
            return None
            
        except Exception as e:
            logger.debug(f"SNMPv3 failed: {str(e)}")
            return None
    
    def _apply_anti_flickering(self, pdu_name, current_reading):
        """Apply anti-flickering logic to prevent readings from jumping to 0"""
        if pdu_name not in self.last_readings:
            self.last_readings[pdu_name] = {
                'last_good': current_reading,
                'last_time': time.time(),
                'zero_count': 0,
                'last_non_zero': current_reading
            }
            return current_reading
        
        last_data = self.last_readings[pdu_name]
        current_time = time.time()
        
        # If current reading is 0, check if it's a flicker
        if current_reading == 0:
            last_data['zero_count'] += 1
            
            # Always use the last good reading instead of 0
            # This prevents flickering and ensures we always have meaningful data
            if last_data['last_good'] > 0:
                unit = "A" if last_data['last_good'] < 100 else "W"
                logger.info(f"🔄 Anti-flickering: Using last good reading {last_data['last_good']:.1f}{unit} instead of 0")
                return last_data['last_good']
            else:
                # If we've never had a good reading, return None to indicate no data
                logger.warning(f"⚠️ No previous good readings available, skipping 0 reading")
                return None
        else:
            # Reset zero count and update last good reading
            last_data['zero_count'] = 0
            last_data['last_good'] = current_reading
            last_data['last_time'] = current_time
            last_data['last_non_zero'] = current_reading
            return current_reading
    
    def collect_all_pdus(self):
        """Collect power readings from all configured PDUs and store in database"""
        logger.info("Starting PDU power collection...")
        
        # Import here to avoid circular imports
        from app import create_app
        from models import db, PDU, PowerReading
        
        app = create_app()
        
        with app.app_context():
            for pdu_key, pdu_config in PDUS.items():
                try:
                    # Get power reading
                    power_data = self.get_power_reading(pdu_config)
                    
                    if power_data:
                        logger.info(f"✅ {pdu_config['name']}: {power_data['power_watts']:.2f}W ({power_data['power_kw']:.3f}kW)")
                        
                        # Store in database
                        try:
                            # Find or create PDU record
                            pdu = PDU.query.filter_by(ip_address=pdu_config['ip']).first()
                            if not pdu:
                                pdu = PDU(
                                    name=pdu_config['name'],
                                    ip_address=pdu_config['ip']
                                )
                                db.session.add(pdu)
                                db.session.commit()
                                logger.info(f"Created new PDU record: {pdu_config['name']}")
                            
                            # Create power reading record
                            reading = PowerReading(
                                pdu_id=pdu.id,
                                timestamp=datetime.utcnow(),
                                power_watts=power_data['power_watts'],
                                power_kw=power_data['power_kw']
                            )
                            db.session.add(reading)
                            db.session.commit()
                            
                            logger.info(f"💾 Stored reading in database: {power_data['power_watts']:.1f}W")
                            
                        except Exception as db_error:
                            logger.error(f"Database error storing reading for {pdu_config['name']}: {str(db_error)}")
                            db.session.rollback()
                            continue
                            
                    else:
                        logger.warning(f"⚠️ No power data collected from {pdu_config['name']}")
                        
                except Exception as e:
                    logger.error(f"❌ Error processing {pdu_config['name']}: {str(e)}")
                    continue
        
        logger.info("Power collection completed successfully")

def main():
    """Main function for standalone execution"""
    collector = PDUCollector()
    collector.collect_all_pdus()

if __name__ == "__main__":
    main()
