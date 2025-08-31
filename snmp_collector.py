#!/usr/bin/env python3
"""
SNMP Collector for APC PDU Power Monitoring
Collects power consumption data from APC PDUs via SNMPv3
"""

import time
import logging
from datetime import datetime, timedelta
from easysnmp import Session
from config import PDUS, SNMP_PORT, SNMP_TIMEOUT, SNMP_RETRIES, POWER_OID
from models import db, PDU, PowerReading
import traceback

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
        pass
    
    def get_power_reading(self, pdu_config):
        """Get power reading from a single PDU"""
        try:
            # Create SNMP session with easysnmp
            session = Session(
                hostname=pdu_config['ip'],
                version=3,
                security_level='authPriv',
                security_username=pdu_config['username'],
                auth_protocol=pdu_config['auth_protocol'].lower(),
                auth_password=pdu_config['auth_passphrase'],
                privacy_protocol=pdu_config['privacy_protocol'].lower(),
                privacy_password=pdu_config['privacy_passphrase'],
                timeout=SNMP_TIMEOUT,
                retries=SNMP_RETRIES
            )
            
            # Perform SNMP GET request
            result = session.get(POWER_OID)
            
            if result:
                power_watts = float(result.value)
                power_kw = power_watts / 1000.0
                
                logger.info(f"{pdu_config['name']}: {power_watts:.2f}W ({power_kw:.3f}kW)")
                return {
                    'power_watts': power_watts,
                    'power_kw': power_kw
                }
            else:
                logger.error(f"No response from {pdu_config['name']}")
                return None
                    
        except Exception as e:
            logger.error(f"Error collecting from {pdu_config['name']}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def collect_all_pdus(self):
        """Collect power readings from all configured PDUs"""
        logger.info("Starting PDU power collection...")
        
        for pdu_key, pdu_config in PDUS.items():
            try:
                # Get power reading
                power_data = self.get_power_reading(pdu_config)
                
                if power_data:
                    # Find PDU in database
                    pdu = PDU.query.filter_by(ip_address=pdu_config['ip']).first()
                    
                    if pdu:
                        # Create power reading record
                        reading = PowerReading(
                            pdu_id=pdu.id,
                            timestamp=datetime.utcnow(),
                            power_watts=power_data['power_watts'],
                            power_kw=power_data['power_kw']
                        )
                        
                        db.session.add(reading)
                        logger.info(f"Stored reading for {pdu_config['name']}: {power_data['power_watts']:.2f}W")
                    else:
                        logger.error(f"PDU {pdu_config['name']} not found in database")
                else:
                    logger.warning(f"No power data collected from {pdu_config['name']}")
                    
            except Exception as e:
                logger.error(f"Error processing {pdu_config['name']}: {str(e)}")
                continue
        
        try:
            db.session.commit()
            logger.info("Power collection completed successfully")
        except Exception as e:
            logger.error(f"Error committing to database: {str(e)}")
            db.session.rollback()

def main():
    """Main function for standalone execution"""
    collector = PDUCollector()
    collector.collect_all_pdus()

if __name__ == "__main__":
    main()

