#!/usr/bin/env python3
"""
Raritan PDU SNMP Data Collector
Collects power consumption data from Raritan PDU PX3-5892 via SNMP
"""

import time
import logging
from datetime import datetime
from easysnmp import Session
from config import RARITAN_CONFIG, RARITAN_OIDS, COLLECTION_INTERVAL
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
        self.setup_database()
        self.setup_snmp_session()
        
    def setup_database(self):
        """Initialize database connection"""
        try:
            db.init_app(None)  # We'll handle the app context manually
            with db.app.app_context():
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
        """Setup SNMP session for Raritan PDU"""
        try:
            self.session = Session(
                hostname=RARITAN_CONFIG['ip'],
                community=RARITAN_CONFIG['snmp_community'],
                version=2,
                timeout=RARITAN_CONFIG['snmp_timeout'],
                retries=RARITAN_CONFIG['snmp_retries']
            )
            logger.info(f"SNMP session established with {RARITAN_CONFIG['ip']}")
        except Exception as e:
            logger.error(f"Error setting up SNMP session: {str(e)}")
            raise
    
    def get_snmp_value(self, oid, port_number=None):
        """Get SNMP value with optional port number substitution"""
        try:
            if port_number:
                oid = oid.format(port=port_number)
            
            result = self.session.get(oid)
            if result and result.value:
                return float(result.value)
            return 0.0
        except Exception as e:
            logger.warning(f"Error getting SNMP value for OID {oid}: {str(e)}")
            return 0.0
    
    def collect_total_power(self):
        """Collect total PDU power consumption"""
        try:
            total_power_watts = self.get_snmp_value(RARITAN_OIDS['total_power_watts'])
            total_power_kw = total_power_watts / 1000.0
            
            # Create power reading record
            with db.app.app_context():
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
    
    def collect_port_power(self, port):
        """Collect power consumption and status for a specific port/outlet"""
        try:
            # Get port power data using outlet OIDs
            power_watts = self.get_snmp_value(RARITAN_OIDS['outlet_power_watts'], port.port_number)
            power_kw = power_watts / 1000.0
            current_amps = self.get_snmp_value(RARITAN_OIDS['outlet_current'], port.port_number)
            voltage = self.get_snmp_value(RARITAN_OIDS['outlet_voltage'], port.port_number)
            power_factor = self.get_snmp_value(RARITAN_OIDS['outlet_power_factor'], port.port_number)
            
            # Get outlet status (on/off)
            outlet_status = self.get_snmp_value(RARITAN_OIDS['outlet_status'], port.port_number)
            is_on = outlet_status > 0 if outlet_status is not None else False
            
            # Get outlet name from PDU (if available)
            outlet_name = self.get_snmp_value(RARITAN_OIDS['outlet_name'], port.port_number)
            if outlet_name and outlet_name != port.name:
                port.name = str(outlet_name)
                db.session.commit()
            
            # Create port power reading record
            with db.app.app_context():
                port_reading = PortPowerReading(
                    port_id=port.id,
                    timestamp=datetime.utcnow(),
                    power_watts=power_watts,
                    power_kw=power_kw,
                    current_amps=current_amps if current_amps > 0 else None,
                    voltage=voltage if voltage > 0 else None,
                    power_factor=power_factor if power_factor > 0 else None
                )
                db.session.add(port_reading)
                db.session.commit()
                
            status_text = "ON" if is_on else "OFF"
            logger.info(f"Outlet {port.port_number} ({port.name}): {power_watts:.1f}W - {status_text}")
            return power_watts
            
        except Exception as e:
            logger.error(f"Error collecting power for outlet {port.port_number}: {str(e)}")
            return 0.0
    
    def collect_all_data(self):
        """Collect all power consumption data"""
        try:
            logger.info("Starting data collection...")
            
            # Collect total PDU power
            total_power = self.collect_total_power()
            
            # Collect individual port power
            port_powers = []
            for port in self.ports:
                port_power = self.collect_port_power(port)
                port_powers.append(port_power)
            
            # Verify total matches sum of ports (with some tolerance)
            sum_port_powers = sum(port_powers)
            if total_power > 0 and abs(total_power - sum_port_powers) > total_power * 0.1:  # 10% tolerance
                logger.warning(f"Total power ({total_power:.1f}W) doesn't match sum of ports ({sum_port_powers:.1f}W)")
            
            logger.info(f"Data collection completed. Total: {total_power:.1f}W, Ports: {len(port_powers)}")
            
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
