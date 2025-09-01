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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to power readings
    power_readings = db.relationship('PowerReading', backref='pdu', lazy=True)
    
    def __repr__(self):
        return f'<PDU {self.name} ({self.ip_address})>'

class PowerReading(db.Model):
    __tablename__ = 'power_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    pdu_id = db.Column(db.Integer, db.ForeignKey('pdus.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    power_watts = db.Column(db.Float, nullable=False)
    power_kw = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<PowerReading {self.power_watts}W at {self.timestamp}>'

class PowerAggregation(db.Model):
    __tablename__ = 'power_aggregations'
    
    id = db.Column(db.Integer, primary_key=True)
    pdu_id = db.Column(db.Integer, db.ForeignKey('pdus.id'), nullable=True)  # NULL for combined
    period_type = db.Column(db.String(20), nullable=False)  # hourly, daily, monthly
    period_start = db.Column(db.DateTime, nullable=False, index=True)
    period_end = db.Column(db.DateTime, nullable=False)
    total_kwh = db.Column(db.Float, nullable=False)
    avg_power_watts = db.Column(db.Float, nullable=False)
    max_power_watts = db.Column(db.Float, nullable=False)
    min_power_watts = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<PowerAggregation {self.period_type} {self.total_kwh}kWh>'

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
    # Check database integrity before initializing
    if check_database_integrity():
        print("Database already exists with data. Skipping initialization.")
        return
    
    print("Initializing new database...")
    db.create_all()
    
    # Create PDU records if they don't exist
    from config import PDUS
    for pdu_key, pdu_config in PDUS.items():
        existing_pdu = PDU.query.filter_by(ip_address=pdu_config['ip']).first()
        if not existing_pdu:
            pdu = PDU(
                name=pdu_config['name'],
                ip_address=pdu_config['ip']
            )
            db.session.add(pdu)
    
    db.session.commit()
    print("Database initialization completed.")

