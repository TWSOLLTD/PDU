#!/usr/bin/env python3
"""
PDU Power Monitoring Web Application
Flask-based web interface for monitoring APC PDU power consumption
"""

from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import logging

from config import DATABASE_URI, FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from models import db, PDU, PowerReading, PowerAggregation, init_db
from data_processor import PowerDataProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Initialize data processor
data_processor = PowerDataProcessor()

@app.route('/')
def index():
    """Main dashboard page"""
    try:
        # Get all PDUs
        pdus = PDU.query.all()
        
        # Get current power readings
        current_readings = {}
        for pdu in pdus:
            latest = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
            if latest:
                current_readings[pdu.id] = {
                    'power_watts': latest.power_watts,
                    'power_kw': latest.power_kw,
                    'timestamp': latest.timestamp
                }
        
        return render_template('index.html', pdus=pdus, current_readings=current_readings)
        
    except Exception as e:
        logger.error(f"Error rendering index: {str(e)}")
        return "Error loading dashboard", 500

@app.route('/api/power-data')
def get_power_data():
    """API endpoint to get power consumption data"""
    try:
        period = request.args.get('period', 'day')
        pdu_ids = request.args.getlist('pdu_ids[]')
        
        # Convert pdu_ids to integers if provided
        if pdu_ids:
            pdu_ids = [int(pid) for pid in pdu_ids if pid.isdigit()]
        
        # Get power summary data
        data = data_processor.get_power_summary(period, pdu_ids)
        
        # Format data for charts
        chart_data = {
            'labels': [],
            'kwh': [],
            'avg_power': [],
            'max_power': [],
            'min_power': []
        }
        
        for item in data:
            if period == 'day':
                label = item['period_start'].strftime('%H:%M')
            elif period == 'week':
                label = item['period_start'].strftime('%Y-%m-%d')
            elif period == 'month':
                label = item['period_start'].strftime('%Y-%m-%d')
            elif period == 'year':
                label = item['period_start'].strftime('%Y-%m')
            
            chart_data['labels'].append(label)
            chart_data['kwh'].append(round(item['total_kwh'], 3))
            chart_data['avg_power'].append(round(item['avg_power_watts'], 1))
            chart_data['max_power'].append(round(item['max_power_watts'], 1))
            chart_data['min_power'].append(round(item['min_power_watts'], 1))
        
        return jsonify({
            'success': True,
            'data': chart_data,
            'period': period
        })
        
    except Exception as e:
        logger.error(f"Error getting power data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/current-status')
def get_current_status():
    """API endpoint to get current PDU status"""
    try:
        pdus = PDU.query.all()
        status_data = []
        
        for pdu in pdus:
            latest = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
            
            if latest:
                status_data.append({
                    'id': pdu.id,
                    'name': pdu.name,
                    'ip': pdu.ip_address,
                    'current_power_watts': latest.power_watts,
                    'current_power_kw': latest.power_kw,
                    'last_reading': latest.timestamp.isoformat(),
                    'status': 'online' if (datetime.utcnow() - latest.timestamp).seconds < 300 else 'offline'
                })
            else:
                status_data.append({
                    'id': pdu.id,
                    'name': pdu.name,
                    'ip': pdu.ip_address,
                    'current_power_watts': 0,
                    'current_power_kw': 0,
                    'last_reading': None,
                    'status': 'no_data'
                })
        
        return jsonify({
            'success': True,
            'data': status_data
        })
        
    except Exception as e:
        logger.error(f"Error getting current status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/statistics')
def get_statistics():
    """API endpoint to get power consumption statistics"""
    try:
        period = request.args.get('period', 'day')
        pdu_ids = request.args.getlist('pdu_ids[]')
        
        # Convert pdu_ids to integers if provided
        if pdu_ids:
            pdu_ids = [int(pid) for pid in pdu_ids if pid.isdigit()]
        
        # Get power summary data
        data = data_processor.get_power_summary(period, pdu_ids)
        
        if not data:
            return jsonify({
                'success': True,
                'data': {
                    'total_kwh': 0,
                    'avg_power_watts': 0,
                    'max_power_watts': 0,
                    'min_power_watts': 0,
                    'peak_hour': None
                }
            })
        
        # Calculate statistics
        total_kwh = sum(item['total_kwh'] for item in data)
        avg_power = sum(item['avg_power_watts'] for item in data) / len(data)
        max_power = max(item['max_power_watts'] for item in data)
        min_power = min(item['min_power_watts'] for item in data)
        
        # Find peak hour
        peak_item = max(data, key=lambda x: x['total_kwh'])
        peak_hour = peak_item['period_start'].strftime('%Y-%m-%d %H:%M')
        
        return jsonify({
            'success': True,
            'data': {
                'total_kwh': round(total_kwh, 3),
                'avg_power_watts': round(avg_power, 1),
                'max_power_watts': round(max_power, 1),
                'min_power_watts': round(min_power, 1),
                'peak_hour': peak_hour
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/pdus')
def get_pdus():
    """API endpoint to get list of PDUs"""
    try:
        pdus = PDU.query.all()
        pdu_list = [{'id': pdu.id, 'name': pdu.name, 'ip': pdu.ip_address} for pdu in pdus]
        
        return jsonify({
            'success': True,
            'data': pdu_list
        })
        
    except Exception as e:
        logger.error(f"Error getting PDUs: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404

@app.errorhandler(500)
def internal_error(error):
    return "Internal server error", 500

def create_app():
    """Application factory function"""
    with app.app_context():
        init_db()
        logger.info("Database initialized successfully")
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)

