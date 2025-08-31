from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import sqlite3

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

def init_db():
    """Initialize the database and create tables"""
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

