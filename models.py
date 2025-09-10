from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import sqlite3
import os
import json

db = SQLAlchemy()

class PDU(db.Model):
    __tablename__ = 'pdus'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(15), nullable=False, unique=True)
    model = db.Column(db.String(50), nullable=False, default='Raritan PX3-5892')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to ports and power readings
    ports = db.relationship('PDUPort', backref='pdu', lazy=True, cascade='all, delete-orphan')
    power_readings = db.relationship('PowerReading', backref='pdu', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<PDU {self.name} ({self.ip_address})>'

class PDUPort(db.Model):
    __tablename__ = 'pdu_ports'
    
    id = db.Column(db.Integer, primary_key=True)
    pdu_id = db.Column(db.Integer, db.ForeignKey('pdus.id'), nullable=False)
    port_number = db.Column(db.Integer, nullable=False)  # Port number (1-36 for PX3-5892)
    name = db.Column(db.String(100), nullable=False)  # User-defined port name
    description = db.Column(db.String(200), nullable=True)  # Optional description
    is_active = db.Column(db.Boolean, default=True)  # Whether port is being monitored
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to power readings
    power_readings = db.relationship('PortPowerReading', backref='port', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<PDUPort {self.name} (Port {self.port_number})>'

class PowerReading(db.Model):
    __tablename__ = 'power_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    pdu_id = db.Column(db.Integer, db.ForeignKey('pdus.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    total_power_watts = db.Column(db.Float, nullable=False)  # Total PDU power
    total_power_kw = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<PowerReading {self.total_power_watts}W at {self.timestamp}>'

class PortPowerReading(db.Model):
    __tablename__ = 'port_power_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    port_id = db.Column(db.Integer, db.ForeignKey('pdu_ports.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    power_watts = db.Column(db.Float, nullable=False)
    power_kw = db.Column(db.Float, nullable=False)
    current_amps = db.Column(db.Float, nullable=True)  # Current in amps
    voltage = db.Column(db.Float, nullable=True)  # Voltage
    power_factor = db.Column(db.Float, nullable=True)  # Power factor
    status = db.Column(db.String(10), nullable=True)  # ON/OFF status
    
    def __repr__(self):
        return f'<PortPowerReading {self.power_watts}W at {self.timestamp}>'

class PowerAggregation(db.Model):
    __tablename__ = 'power_aggregations'
    
    id = db.Column(db.Integer, primary_key=True)
    pdu_id = db.Column(db.Integer, db.ForeignKey('pdus.id'), nullable=True)  # NULL for combined
    port_id = db.Column(db.Integer, db.ForeignKey('pdu_ports.id'), nullable=True)  # NULL for PDU total
    period_type = db.Column(db.String(20), nullable=False)  # hourly, daily, monthly, yearly
    period_start = db.Column(db.DateTime, nullable=False, index=True)
    period_end = db.Column(db.DateTime, nullable=False)
    total_kwh = db.Column(db.Float, nullable=False)
    avg_power_watts = db.Column(db.Float, nullable=False)
    max_power_watts = db.Column(db.Float, nullable=False)
    min_power_watts = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<PowerAggregation {self.period_type} {self.total_kwh}kWh>'

class OutletGroup(db.Model):
    __tablename__ = 'outlet_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    outlet_ids = db.Column(db.Text, nullable=False)  # JSON string of outlet IDs
    color = db.Column(db.String(7), nullable=True)  # Hex color code for charts
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<OutletGroup {self.name}>'
    
    def get_outlet_ids(self):
        """Get outlet IDs as a list"""
        try:
            return json.loads(self.outlet_ids)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_outlet_ids(self, outlet_ids):
        """Set outlet IDs from a list"""
        self.outlet_ids = json.dumps(outlet_ids)
    
    def add_outlet(self, outlet_id):
        """Add an outlet to this group"""
        current_ids = self.get_outlet_ids()
        if outlet_id not in current_ids:
            current_ids.append(outlet_id)
            self.set_outlet_ids(current_ids)
    
    def remove_outlet(self, outlet_id):
        """Remove an outlet from this group"""
        current_ids = self.get_outlet_ids()
        if outlet_id in current_ids:
            current_ids.remove(outlet_id)
            self.set_outlet_ids(current_ids)

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False, unique=True)
    value = db.Column(db.Text, nullable=True)  # Store as JSON string for complex data
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemSettings {self.key}={self.value}>'
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value, return default if not found"""
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            return default
        
        # Try to parse as JSON, fall back to string
        try:
            return json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            return setting.value
    
    @classmethod
    def set_setting(cls, key, value):
        """Set a setting value"""
        setting = cls.query.filter_by(key=key).first()
        
        # Convert value to JSON string if it's not a string
        if not isinstance(value, str):
            value = json.dumps(value)
        
        if setting is None:
            setting = cls(key=key, value=value)
            db.session.add(setting)
        else:
            setting.value = value
        
        db.session.commit()
        return setting

def check_database_integrity():
    """Check if database has existing data before initializing"""
    try:
        # Check if database file exists and has data
        db_path = 'pdu_monitor.db'
        if os.path.exists(db_path):
            # Check file size (if it's very small, it might be empty)
            file_size = os.path.getsize(db_path)
            if file_size < 1024:  # Less than 1KB
                print(f"Warning: Database file is very small ({file_size} bytes). It might be empty or corrupted.")
                return False
            
            # Try to connect and check for existing data
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            if not tables:
                print("Warning: Database file exists but contains no tables.")
                return False
            
            # Check if we have any power readings
            cursor.execute("SELECT COUNT(*) FROM power_readings;")
            reading_count = cursor.fetchone()[0]
            
            if reading_count == 0:
                print("Warning: Database exists but contains no power readings.")
                return False
            
            print(f"Database integrity check passed. Found {reading_count} power readings.")
            conn.close()
            return True
            
    except Exception as e:
        print(f"Database integrity check failed: {str(e)}")
        return False
    
    return False

def init_db():
    """Initialize the database and create tables"""
    print("Initializing new database...")
    
    # Create single PDU record for Raritan PX3-5892
    existing_pdu = PDU.query.first()
    if not existing_pdu:
        pdu = PDU(
            name='Raritan PX3-5892',
            ip_address='172.0.250.9',  # Updated IP address
            model='Raritan PX3-5892'
        )
        db.session.add(pdu)
        db.session.flush()  # Get the ID
        
        # Create outlets for the PX3-5892 (all 36 outlets)
        # All 36 outlets exist in the configuration, but only 7 are accessible for power measurements
        for port_num in range(1, 37):
            port = PDUPort(
                pdu_id=pdu.id,
                port_number=port_num,
                name=f'Outlet {port_num}',
                description=f'Outlet {port_num} on Raritan PX3-5892',
                is_active=True
            )
            db.session.add(port)
    
    db.session.commit()
    print("Database initialization completed.")

