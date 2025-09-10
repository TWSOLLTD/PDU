#!/usr/bin/env python3
"""
Raritan PDU SNMP Data Collector
Collects power consumption data from Raritan PDU PX3-5892 via SNMP
"""

import time
import logging
from datetime import datetime
from flask import Flask
from easysnmp import Session
from config import RARITAN_CONFIG, RARITAN_OIDS, COLLECTION_INTERVAL, DATABASE_URI
from models import db, PDU, PDUPort, PowerReading, PortPowerReading, OutletGroup, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raritan_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RaritanPDUCollector:
    def __init__(self):
        self.session = None
        self.pdu = None
        self.ports = []
        self.app = None
        self.setup_database()
        self.setup_snmp_session()
        
    def setup_database(self):
        """Initialize database connection"""
        try:
            # Create Flask app for database context
            self.app = Flask(__name__)
            self.app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
            self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            
            db.init_app(self.app)
            
            with self.app.app_context():
                init_db()
                self.pdu = PDU.query.first()
                if self.pdu:
                    self.ports = PDUPort.query.filter_by(pdu_id=self.pdu.id, is_active=True).order_by(PDUPort.port_number).all()
                    logger.info(f"Found PDU: {self.pdu.name} with {len(self.ports)} active ports")
                else:
                    logger.error("No PDU found in database")
        except Exception as e:
            logger.error(f"Error setting up database: {str(e)}")
            raise
    
    def setup_snmp_session(self):
        """Setup SNMP v3 session for Raritan PDU"""
        try:
            self.session = Session(
                hostname=RARITAN_CONFIG['ip'],
                security_username=RARITAN_CONFIG['snmp_username'],
                auth_protocol=RARITAN_CONFIG['snmp_auth_protocol'],
                auth_password=RARITAN_CONFIG['snmp_auth_password'],
                privacy_protocol=RARITAN_CONFIG['snmp_priv_protocol'],
                privacy_password=RARITAN_CONFIG['snmp_priv_password'],
                version=3,
                timeout=RARITAN_CONFIG['snmp_timeout'],
                retries=RARITAN_CONFIG['snmp_retries']
            )
            logger.info(f"SNMP v3 session established with {RARITAN_CONFIG['ip']} using user: {RARITAN_CONFIG['snmp_username']}")
        except Exception as e:
            logger.error(f"Error setting up SNMP v3 session: {str(e)}")
            raise
    
    def get_snmp_value(self, oid, port_number=None, as_string=False):
        """Get SNMP value with optional port number substitution"""
        try:
            if port_number:
                oid = oid.format(outlet=port_number)
            
            result = self.session.get(oid)
            if result and result.value:
                # Handle NOSUCHINSTANCE gracefully
                if str(result.value) == 'NOSUCHINSTANCE':
                    return None
                
                # Return as string for names, float for numeric values
                if as_string:
                    return str(result.value)
                else:
                    return float(result.value)
            return None
        except Exception as e:
            logger.warning(f"Error getting SNMP value for OID {oid}: {str(e)}")
            return None
    
    def collect_total_power(self):
        """Collect total PDU power consumption"""
        try:
            total_power_watts = self.get_snmp_value(RARITAN_OIDS['total_power_watts'])
            if total_power_watts is None:
                total_power_watts = 0.0
            total_power_kw = total_power_watts / 1000.0
            
            # Create power reading record
            with self.app.app_context():
                power_reading = PowerReading(
                    pdu_id=self.pdu.id,
                    timestamp=datetime.utcnow(),
                    total_power_watts=total_power_watts,
                    total_power_kw=total_power_kw
                )
                db.session.add(power_reading)
                db.session.commit()
                
            logger.info(f"Total PDU power: {total_power_watts:.1f}W ({total_power_kw:.3f}kW)")
            return total_power_watts
            
        except Exception as e:
            logger.error(f"Error collecting total power: {str(e)}")
            return 0.0
    
    def discover_outlets(self):
        """Discover which outlets actually exist on the PDU"""
        existing_outlets = []
        
        # Try multiple OID patterns to find all outlets - using correct OIDs
        oid_patterns = [
            '1.3.6.1.4.1.13742.6.3.5.3.1.3.1',      # Outlet names (all 36 outlets)
            '1.3.6.1.4.1.13742.6.3.3.4.1.9.1.1',    # Outlet status (7 outlets)
            '1.3.6.1.4.1.13742.6.3.3.4.1.7.1.1',    # Outlet power (7 outlets)
            '1.3.6.1.4.1.13742.6.3.3.4.1.8.1.1',    # Outlet current (7 outlets)
        ]
        
        for pattern in oid_patterns:
            try:
                logger.info(f"Walking OID pattern: {pattern}")
                results = self.session.walk(pattern)
                
                for result in results:
                    # Extract outlet number from OID
                    oid_parts = result.oid.split('.')
                    if len(oid_parts) >= 2:
                        try:
                            outlet_num = int(oid_parts[-1])
                            # Only consider outlets 1-36
                            if 1 <= outlet_num <= 36 and outlet_num not in existing_outlets:
                                existing_outlets.append(outlet_num)
                                logger.debug(f"Found outlet {outlet_num} via {pattern}")
                        except ValueError:
                            continue
                            
                logger.info(f"Found {len(existing_outlets)} outlets from pattern {pattern}: {sorted(existing_outlets)}")
                
            except Exception as e:
                logger.warning(f"Error walking pattern {pattern}: {e}")
                continue
        
        # Since we know from the PDU config that all 36 outlets exist (1-36),
        # force individual check if we don't find all of them
        if len(existing_outlets) < 36:
            logger.warning(f"Only found {len(existing_outlets)} outlets via SNMP walk, but PDU config shows 36 outlets exist")
            logger.info("Forcing individual check for all outlets 1-36")
            return self.check_outlets_individually()
            
        logger.info(f"Total discovered outlets: {len(existing_outlets)} - {sorted(existing_outlets)}")
        return sorted(existing_outlets)

    def check_outlets_individually(self):
        """Fallback method to check outlets 1-36 individually"""
        existing_outlets = []
        
        # All 36 outlets exist in the configuration, but only 7 are accessible for power measurements
        # We'll monitor all 36 outlets, but only 7 will have real-time power data
        
        logger.info("PDU has 36 outlets total - all will be monitored")
        logger.info("7 outlets have real-time power data, 29 outlets will show as offline/inaccessible")
        
        # Add all 36 outlets to the list
        for outlet_num in range(1, 37):
            existing_outlets.append(outlet_num)
            
        logger.info(f"Monitoring all {len(existing_outlets)} outlets: 1-36")
        return existing_outlets

    def collect_port_power(self, port):
        """Collect power consumption and status for a specific port/outlet"""
        try:
            # Get port power data using outlet OIDs
            power_watts = self.get_snmp_value(RARITAN_OIDS['outlet_power_watts'], port.port_number)
            if power_watts is None:
                power_watts = 0.0
            power_kw = power_watts / 1000.0
            
            # Current measurement not available in working OIDs
            current_amps = None
                
            # Note: voltage and power_factor OIDs not available on this PDU model
            voltage = None
            power_factor = None
            
            # Get outlet status (on/off) - 7=ON, 8=OFF
            outlet_status = self.get_snmp_value(RARITAN_OIDS['outlet_status'], port.port_number)
            is_on = outlet_status == 7 if outlet_status is not None else False
            
            # Log if we can't read data from this outlet
            if power_watts == 0.0 and outlet_status is None:
                logger.debug(f"Outlet {port.port_number} appears to be inaccessible via SNMP")
            
            # Get outlet name from PDU using correct OIDs (works for all 36 outlets)
            outlet_name = self.get_snmp_value(RARITAN_OIDS['outlet_name'], port.port_number, as_string=True)
            
            # Update port name if we found a different name
            if outlet_name and outlet_name != port.name and outlet_name != f'Outlet {port.port_number}':
                with self.app.app_context():
                    port.name = outlet_name
                    db.session.commit()
                    logger.info(f"Updated outlet {port.port_number} name to: {outlet_name}")
            
            # Log the outlet status with correct name
            logger.info(f"Outlet {port.port_number} ({outlet_name}): {power_watts}W - {'ON' if is_on else 'OFF'}")
            
            # Create port power reading record
            with self.app.app_context():
                port_reading = PortPowerReading(
                    port_id=port.id,
                    timestamp=datetime.utcnow(),
                    power_watts=power_watts,
                    power_kw=power_kw,
                    current_amps=current_amps if current_amps and current_amps > 0 else None,
                    voltage=voltage if voltage and voltage > 0 else None,
                    power_factor=power_factor if power_factor and power_factor > 0 else None
                )
                db.session.add(port_reading)
                db.session.commit()
                
            status_text = "ON" if is_on else "OFF"
            logger.info(f"Outlet {port.port_number} ({port.name}): {power_watts:.1f}W - {status_text} (Status: {outlet_status})")
            return power_watts
            
        except Exception as e:
            logger.error(f"Error collecting power for outlet {port.port_number}: {str(e)}")
            return 0.0
    
    def collect_all_data(self):
        """Collect all power consumption data"""
        try:
            logger.info("Starting data collection...")
            
            # Discover which outlets actually exist on the PDU
            existing_outlets = self.discover_outlets()
            
            # Collect total PDU power
            total_power = self.collect_total_power()
            
            # Collect individual port power only for existing outlets
            port_powers = []
            for port in self.ports:
                if port.port_number in existing_outlets:
                    port_power = self.collect_port_power(port)
                    port_powers.append(port_power)
                else:
                    logger.debug(f"Skipping outlet {port.port_number} - not found on PDU")
            
            # Verify total matches sum of ports (with some tolerance)
            sum_port_powers = sum(port_powers)
            if total_power > 0 and abs(total_power - sum_port_powers) > total_power * 0.1:  # 10% tolerance
                logger.warning(f"Total power ({total_power:.1f}W) doesn't match sum of ports ({sum_port_powers:.1f}W)")
            
            logger.info(f"Data collection completed. Total: {total_power:.1f}W, Active Ports: {len(port_powers)}/{len(existing_outlets)}")
            
        except Exception as e:
            logger.error(f"Error in data collection: {str(e)}")
    
    def run(self):
        """Main collection loop"""
        logger.info("Raritan PDU Data Collector started")
        logger.info(f"Collection interval: {COLLECTION_INTERVAL} seconds")
        
        while True:
            try:
                self.collect_all_data()
                time.sleep(COLLECTION_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Data collection stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                time.sleep(COLLECTION_INTERVAL)

def collect_power_data():
    """Simple function to collect power data - called from main app"""
    try:
        collector = RaritanPDUCollector()
        collector.collect_all_data()
    except Exception as e:
        logger.error(f"Error collecting power data: {str(e)}")
        raise

def main():
    """Main entry point"""
    try:
        collector = RaritanPDUCollector()
        collector.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == '__main__':
    main()
