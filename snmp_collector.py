#!/usr/bin/env python3
"""
Raritan PDU SNMP Data Collector
Collects power consumption data from Raritan PDU PX3-5892 via SNMP
"""

import time
import logging
import subprocess
from datetime import datetime
from flask import Flask
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
    def __init__(self, app=None):
        self.pdu = None
        self.ports = []
        self.app = app
        if app:
            self.setup_database_with_app(app)
        else:
            self.setup_database()
        
    def setup_database_with_app(self, app):
        """Initialize database connection using existing Flask app"""
        try:
            self.app = app
            
            with self.app.app_context():
                self.pdu = PDU.query.first()
                if self.pdu:
                    self.ports = PDUPort.query.filter_by(pdu_id=self.pdu.id, is_active=True).order_by(PDUPort.port_number).all()
                    logger.info(f"Found PDU: {self.pdu.name} with {len(self.ports)} active ports")
                else:
                    logger.error("No PDU found in database")
        except Exception as e:
            logger.error(f"Error setting up database with app: {str(e)}")
            raise

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
    
    def execute_snmp_command(self, command):
        """Execute exact SNMP command and return the result"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Extract the value from the SNMP response
                # Format: "SNMPv2-SMI::enterprises.13742.6.5.2.3.1.4.1.1.5 = INTEGER: 1234"
                # Format: "SNMPv2-SMI::enterprises.13742.6.5.4.3.1.4.1.35.5 = Gauge32: 43"
                # Format: "SNMPv2-SMI::enterprises.13742.6.3.5.3.1.3.1.1 = STRING: "Server 1""
                logger.debug(f"SNMP command output: {result.stdout.strip()}")
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if '=' in line:
                        value_part = line.split('=')[1].strip()
                        logger.debug(f"Parsing value part: '{value_part}'")
                        # Handle different SNMP data types
                        if 'INTEGER:' in value_part:
                            return int(value_part.split('INTEGER:')[1].strip())
                        elif 'Gauge32:' in value_part:
                            return int(value_part.split('Gauge32:')[1].strip())
                        elif 'Counter32:' in value_part:
                            return int(value_part.split('Counter32:')[1].strip())
                        elif 'STRING:' in value_part:
                            name_value = value_part.split('STRING:')[1].strip().strip('"')
                            logger.debug(f"Extracted STRING value: '{name_value}'")
                            return name_value
                        elif 'Hex-STRING:' in value_part:
                            return value_part.split('Hex-STRING:')[1].strip()
                        else:
                            # Try to extract numeric value from the end
                            parts = value_part.split()
                            if parts:
                                try:
                                    return int(parts[-1])
                                except ValueError:
                                    return value_part
                return None
            else:
                logger.warning(f"SNMP command failed: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            logger.warning(f"SNMP command timed out: {command}")
            return None
        except Exception as e:
            logger.warning(f"Error executing SNMP command: {str(e)}")
            return None
    
    def get_snmp_value(self, oid_template, port_number=None, as_string=False):
        """Get SNMP value using exact command from your working commands"""
        try:
            # Build the exact command from your working commands
            if port_number:
                oid = oid_template.format(outlet=port_number)
            else:
                oid = oid_template
            
            # Use the EXACT command format from your working commands
            command = f'snmpget -v3 -l authPriv -u snmpuser -a SHA-256 -A "91W1CGVNkhTXA<^W" -x AES-128 -X "91W1CGVNkhTXA<^W" 172.0.250.9 {oid}'
            
            result = self.execute_snmp_command(command)
            if result is not None:
                if as_string:
                    return str(result)
                else:
                    return float(result)
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
        """All 36 outlets exist - we'll check them individually using exact commands"""
        logger.info("Using exact SNMP commands to check all 36 outlets")
        return self.check_outlets_individually()

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
            logger.debug(f"Outlet {port.port_number} name from SNMP: '{outlet_name}' (type: {type(outlet_name)})")
            
            # Update port name if we found a different name
            if outlet_name and outlet_name != port.name and outlet_name != f'Outlet {port.port_number}':
                with self.app.app_context():
                    # Refresh the port object from the database to get current state
                    current_port = PDUPort.query.get(port.id)
                    old_name = current_port.name
                    
                    current_port.name = outlet_name
                    current_port.updated_at = datetime.utcnow()
                    db.session.commit()
                    
                    logger.info(f"Updated outlet {port.port_number} name from '{old_name}' to: '{outlet_name}'")
                    
                    # Verify the update worked
                    updated_port = PDUPort.query.get(port.id)
                    logger.info(f"Verification - outlet {port.port_number} name in DB: '{updated_port.name}'")
                    
                    # Update the local port object to reflect the change
                    port.name = outlet_name
            elif outlet_name == '' or outlet_name is None:
                logger.debug(f"Outlet {port.port_number} has no custom name, keeping default")
            
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

def collect_power_data(app=None):
    """Simple function to collect power data - called from main app"""
    try:
        collector = RaritanPDUCollector(app)
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
