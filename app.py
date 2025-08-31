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
            'power_watts': []
        }
        
        for item in data:
            if period == 'hour':
                label = item['period_start'].strftime('%H:%M')
            elif period == 'day':
                label = item['period_start'].strftime('%H:%M')
            elif period == 'week':
                label = item['period_start'].strftime('%Y-%m-%d')
            elif period == 'month':
                label = item['period_start'].strftime('%Y-%m-%d')
            else:
                label = item['period_start'].strftime('%Y-%m-%d')
            
            chart_data['labels'].append(label)
            chart_data['power_watts'].append(round(item['avg_power_watts'], 1))
        
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
    """API endpoint to get current PDU status and power readings"""
    try:
        # Get all PDUs
        pdus = PDU.query.all()
        
        # Get current power readings and calculate statistics
        pdu_status = []
        total_power_watts = 0
        online_pdus = 0
        
        for pdu in pdus:
            latest = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
            
            if latest:
                # Check if reading is recent (within last 5 minutes)
                time_diff = datetime.utcnow() - latest.timestamp
                online = time_diff.total_seconds() < 300  # 5 minutes
                
                if online:
                    online_pdus += 1
                    total_power_watts += latest.power_watts
                
                pdu_status.append({
                    'id': pdu.id,
                    'name': pdu.name,
                    'ip_address': pdu.ip_address,
                    'online': online,
                    'current_power_watts': latest.power_watts,
                    'current_power_kw': latest.power_kw,
                    'last_reading': latest.timestamp.isoformat()
                })
            else:
                pdu_status.append({
                    'id': pdu.id,
                    'name': pdu.name,
                    'ip_address': pdu.ip_address,
                    'online': False,
                    'current_power_watts': 0,
                    'current_power_kw': 0,
                    'last_reading': None
                })
        
        # Calculate total energy for today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_readings = PowerReading.query.filter(PowerReading.timestamp >= today_start).all()
        total_energy_kwh = sum(reading.power_kw for reading in today_readings) / 60  # Convert to kWh (assuming 1-minute intervals)
        
        # Get peak power for today
        peak_power_watts = 0
        if today_readings:
            peak_power_watts = max(reading.power_watts for reading in today_readings)
        
        statistics = {
            'total_power_watts': total_power_watts,
            'total_energy_kwh': total_energy_kwh,
            'peak_power_watts': peak_power_watts,
            'online_pdus': online_pdus
        }
        
        return jsonify({
            'success': True,
            'pdus': pdu_status,
            'statistics': statistics
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

@app.route('/api/energy-data')
def get_energy_data():
    """API endpoint to get energy consumption data"""
    try:
        period = request.args.get('period', 'day')
        
        # Get energy data for the specified period
        if period == 'day':
            # Get hourly energy consumption for today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            readings = PowerReading.query.filter(PowerReading.timestamp >= today_start).all()
            
            # Group by hour
            hourly_data = {}
            for reading in readings:
                hour = reading.timestamp.replace(minute=0, second=0, microsecond=0)
                if hour not in hourly_data:
                    hourly_data[hour] = []
                hourly_data[hour].append(reading.power_kw)
            
            # Calculate energy for each hour
            chart_data = {
                'labels': [],
                'energy_kwh': []
            }
            
            for hour in sorted(hourly_data.keys()):
                chart_data['labels'].append(hour.strftime('%H:00'))
                # Sum power readings and convert to kWh (assuming 1-minute intervals)
                energy_kwh = sum(hourly_data[hour]) / 60
                chart_data['energy_kwh'].append(round(energy_kwh, 3))
        
        elif period == 'week':
            # Get daily energy consumption for the last 7 days
            week_start = datetime.utcnow() - timedelta(days=7)
            readings = PowerReading.query.filter(PowerReading.timestamp >= week_start).all()
            
            # Group by day
            daily_data = {}
            for reading in readings:
                day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                if day not in daily_data:
                    daily_data[day] = []
                daily_data[day].append(reading.power_kw)
            
            chart_data = {
                'labels': [],
                'energy_kwh': []
            }
            
            for day in sorted(daily_data.keys()):
                chart_data['labels'].append(day.strftime('%Y-%m-%d'))
                energy_kwh = sum(daily_data[day]) / 60
                chart_data['energy_kwh'].append(round(energy_kwh, 3))
        
        elif period == 'month':
            # Get daily energy consumption for the last 30 days
            month_start = datetime.utcnow() - timedelta(days=30)
            readings = PowerReading.query.filter(PowerReading.timestamp >= month_start).all()
            
            # Group by day
            daily_data = {}
            for reading in readings:
                day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                if day not in daily_data:
                    daily_data[day] = []
                daily_data[day].append(reading.power_kw)
            
            chart_data = {
                'labels': [],
                'energy_kwh': []
            }
            
            for day in sorted(daily_data.keys()):
                chart_data['labels'].append(day.strftime('%Y-%m-%d'))
                energy_kwh = sum(daily_data[day]) / 60
                chart_data['energy_kwh'].append(round(energy_kwh, 3))
        
        return jsonify({
            'success': True,
            'data': chart_data,
            'period': period
        })
        
    except Exception as e:
        logger.error(f"Error getting energy data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export-data')
def export_data():
    """API endpoint to export power data as CSV"""
    try:
        period = request.args.get('period', 'day')
        format_type = request.args.get('format', 'csv')
        
        if format_type == 'csv':
            # Get power readings for the specified period
            if period == 'day':
                start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == 'week':
                start_time = datetime.utcnow() - timedelta(days=7)
            elif period == 'month':
                start_time = datetime.utcnow() - timedelta(days=30)
            else:
                start_time = datetime.utcnow() - timedelta(days=1)
            
            readings = PowerReading.query.filter(PowerReading.timestamp >= start_time).order_by(PowerReading.timestamp).all()
            
            # Create CSV content
            csv_content = "Timestamp,PDU,Power (Watts),Power (kW)\n"
            
            for reading in readings:
                pdu = PDU.query.get(reading.pdu_id)
                pdu_name = pdu.name if pdu else f"PDU-{reading.pdu_id}"
                csv_content += f"{reading.timestamp},{pdu_name},{reading.power_watts},{reading.power_kw}\n"
            
            from flask import Response
            return Response(
                csv_content,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=pdu-power-data-{period}-{datetime.utcnow().strftime("%Y%m%d")}.csv'}
            )
        
        return jsonify({
            'success': False,
            'error': 'Unsupported format'
        }), 400
        
    except Exception as e:
        logger.error(f"Error exporting data: {str(e)}")
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

