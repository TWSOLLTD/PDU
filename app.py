#!/usr/bin/env python3
"""
Raritan PDU Power Monitoring Web Application
Flask-based web interface for monitoring Raritan PDU PX3-5892 power consumption
"""

from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import logging
import requests
from sqlalchemy import func, and_

from config import DATABASE_URI, FLASK_HOST, FLASK_PORT, FLASK_DEBUG, RARITAN_CONFIG, GROUP_MANAGEMENT_PASSWORD
from models import db, PDU, PDUPort, PowerReading, PortPowerReading, PowerAggregation, SystemSettings, OutletGroup, init_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

@app.route('/')
def index():
    """Main dashboard page"""
    try:
        # Get the single PDU
        pdu = PDU.query.first()
        if not pdu:
            return "No PDU configured", 404
        
        # Get all active ports
        ports = PDUPort.query.filter_by(pdu_id=pdu.id, is_active=True).order_by(PDUPort.port_number).all()
        
        # Get current power readings
        latest_total = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
        current_total_power = latest_total.total_power_watts if latest_total else 0
        
        # Get latest port readings
        port_readings = {}
        for port in ports:
            latest = PortPowerReading.query.filter_by(port_id=port.id).order_by(PortPowerReading.timestamp.desc()).first()
            if latest:
                port_readings[port.id] = {
                    'power_watts': latest.power_watts,
                    'power_kw': latest.power_kw,
                    'current_amps': latest.current_amps,
                    'voltage': latest.voltage,
                    'power_factor': latest.power_factor,
                    'timestamp': latest.timestamp
                }
            else:
                port_readings[port.id] = {
                    'power_watts': 0,
                    'power_kw': 0,
                    'current_amps': 0,
                    'voltage': 0,
                    'power_factor': 0,
                    'timestamp': None
                }
        
        return render_template('index.html', 
                             pdu=pdu, 
                             ports=ports, 
                             current_total_power=current_total_power,
                             port_readings=port_readings)
        
    except Exception as e:
        logger.error(f"Error rendering index: {str(e)}")
        return "Error loading dashboard", 500

@app.route('/api/current-status')
def get_current_status():
    """API endpoint to get current PDU and port status"""
    try:
        pdu = PDU.query.first()
        if not pdu:
            return jsonify({'success': False, 'error': 'No PDU configured'}), 404
        
        # Get latest total power reading
        latest_total = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
        
        # Get all active ports with their latest readings
        ports = PDUPort.query.filter_by(pdu_id=pdu.id, is_active=True).order_by(PDUPort.port_number).all()
        port_status = []
        total_power_watts = 0
        
        for port in ports:
            latest = PortPowerReading.query.filter_by(port_id=port.id).order_by(PortPowerReading.timestamp.desc()).first()
            
            if latest:
                # Check if reading is recent (within last 5 minutes)
                time_diff = datetime.utcnow() - latest.timestamp
                online = time_diff.total_seconds() < 300  # 5 minutes
                
                if online:
                    total_power_watts += latest.power_watts
                
                port_status.append({
                    'id': port.id,
                    'port_number': port.port_number,
                    'name': port.name,
                    'description': port.description,
                    'online': online,
                    'current_power_watts': latest.power_watts,
                    'current_power_kw': latest.power_kw,
                    'current_amps': latest.current_amps,
                    'voltage': latest.voltage,
                    'power_factor': latest.power_factor,
                    'last_reading': latest.timestamp.isoformat()
                })
            else:
                port_status.append({
                    'id': port.id,
                    'port_number': port.port_number,
                    'name': port.name,
                    'description': port.description,
                    'online': False,
                    'current_power_watts': 0,
                    'current_power_kw': 0,
                    'current_amps': 0,
                    'voltage': 0,
                    'power_factor': 0,
                    'last_reading': None
                })
        
        # Calculate total energy for today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_readings = PowerReading.query.filter(PowerReading.timestamp >= today_start).all()
        
        # Calculate energy consumption (kWh) from power readings
        total_energy_kwh = sum(reading.total_power_kw for reading in today_readings) / 60.0  # Convert to kWh (assuming 1-minute intervals)
        
        # Get peak power for today
        peak_power_watts = 0
        if today_readings:
            peak_power_watts = max(reading.total_power_watts for reading in today_readings)
        
        # Count online ports
        online_ports = sum(1 for port in port_status if port['online'])
        
        return jsonify({
            'success': True,
            'pdu': {
                'id': pdu.id,
                'name': pdu.name,
                'model': pdu.model,
                'ip_address': pdu.ip_address,
                'total_power_watts': total_power_watts,
                'total_power_kw': total_power_watts / 1000,
                'total_energy_kwh': total_energy_kwh,
                'peak_power_watts': peak_power_watts,
                'online_ports': online_ports,
                'total_ports': len(ports)
            },
            'ports': port_status
        })
        
    except Exception as e:
        logger.error(f"Error getting current status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/power-data')
def get_power_data():
    """API endpoint to get power consumption data for charts"""
    try:
        period = request.args.get('period', 'hour')
        view_type = request.args.get('view', 'total')  # 'total' or 'ports'
        
        pdu = PDU.query.first()
        if not pdu:
            return jsonify({'success': False, 'error': 'No PDU configured'}), 404
        
        if view_type == 'total':
            # Get total PDU power data
            if period == 'hour':
                # Get last 24 hours of data aligned to 15-minute boundaries (UTC), then label in UK time
                now_utc = datetime.utcnow()
                end_time = now_utc.replace(minute=(now_utc.minute // 15) * 15, second=0, microsecond=0)
                start_time = end_time - timedelta(hours=24)
                readings = (
                    PowerReading.query
                    .filter(PowerReading.timestamp >= start_time, PowerReading.timestamp <= end_time)
                    .all()
                )
                
                # Group by 15-minute intervals
                interval_data = {}
                for reading in readings:
                    minutes = reading.timestamp.minute
                    rounded_minutes = (minutes // 15) * 15
                    interval = reading.timestamp.replace(minute=rounded_minutes, second=0, microsecond=0)
                    
                    if interval not in interval_data:
                        interval_data[interval] = []
                    interval_data[interval].append(reading.total_power_watts)
                
                chart_data = {
                    'labels': [],
                    'power_watts': []
                }
                
                # Create all 15-minute intervals for the last 24 hours
                for i in range(96):  # 24 hours * 4 intervals per hour
                    target_interval = start_time + timedelta(minutes=15*i)
                    uk_time = target_interval.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/London'))
                    chart_data['labels'].append(uk_time.strftime('%H:%M'))
                    
                    if target_interval in interval_data:
                        avg_power = sum(interval_data[target_interval]) / len(interval_data[target_interval])
                        chart_data['power_watts'].append(round(avg_power, 1))
                    else:
                        chart_data['power_watts'].append(0)
            
            elif period == 'week':
                # Get last 7 days of data, grouped by day
                start_time = datetime.utcnow() - timedelta(days=7)
                readings = PowerReading.query.filter(PowerReading.timestamp >= start_time).all()
                
                # Group by day
                daily_data = {}
                for reading in readings:
                    day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                    if day not in daily_data:
                        daily_data[day] = []
                    daily_data[day].append(reading.total_power_watts)
                
                chart_data = {
                    'labels': [],
                    'power_watts': []
                }
                
                # Create all 7 days
                for i in range(7):
                    target_date = datetime.utcnow() - timedelta(days=6-i)
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                    
                    if target_date in daily_data:
                        avg_power = sum(daily_data[target_date]) / len(daily_data[target_date])
                        chart_data['power_watts'].append(round(avg_power, 1))
                    else:
                        chart_data['power_watts'].append(0)
            
            elif period == 'month':
                # Get last 30 days of data, grouped by day
                start_time = datetime.utcnow() - timedelta(days=30)
                readings = PowerReading.query.filter(PowerReading.timestamp >= start_time).all()
                
                # Group by day
                daily_data = {}
                for reading in readings:
                    day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                    if day not in daily_data:
                        daily_data[day] = []
                    daily_data[day].append(reading.total_power_watts)
                
                chart_data = {
                    'labels': [],
                    'power_watts': []
                }
                
                # Create all 30 days
                for i in range(30):
                    target_date = datetime.utcnow() - timedelta(days=29-i)
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                    
                    if target_date in daily_data:
                        avg_power = sum(daily_data[target_date]) / len(daily_data[target_date])
                        chart_data['power_watts'].append(round(avg_power, 1))
                    else:
                        chart_data['power_watts'].append(0)
            
            elif period == 'year':
                # Get last 12 months of data, grouped by month
                start_time = datetime.utcnow() - timedelta(days=365)
                readings = PowerReading.query.filter(PowerReading.timestamp >= start_time).all()
                
                # Group by month
                monthly_data = {}
                for reading in readings:
                    month = reading.timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    if month not in monthly_data:
                        monthly_data[month] = []
                    monthly_data[month].append(reading.total_power_watts)
                
                chart_data = {
                    'labels': [],
                    'power_watts': []
                }
                
                # Create all 12 months
                for i in range(12):
                    target_month = datetime.utcnow() - timedelta(days=365-30*i)
                    target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_month.strftime('%Y-%m'))
                    
                    if target_month in monthly_data:
                        avg_power = sum(monthly_data[target_month]) / len(monthly_data[target_month])
                        chart_data['power_watts'].append(round(avg_power, 1))
                    else:
                        chart_data['power_watts'].append(0)
            
            return jsonify({
                'success': True,
                'data': chart_data,
                'period': period,
                'view_type': view_type
            })
        
        else:
            # Get individual port data
            ports = PDUPort.query.filter_by(pdu_id=pdu.id, is_active=True).order_by(PDUPort.port_number).all()
            
            if period == 'hour':
                # Get last 24 hours of data for each port
                now_utc = datetime.utcnow()
                end_time = now_utc.replace(minute=(now_utc.minute // 15) * 15, second=0, microsecond=0)
                start_time = end_time - timedelta(hours=24)
                
                chart_data = {
                    'labels': [],
                    'ports': []
                }
                
                # Create all 15-minute intervals for the last 24 hours
                for i in range(96):
                    target_interval = start_time + timedelta(minutes=15*i)
                    uk_time = target_interval.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/London'))
                    chart_data['labels'].append(uk_time.strftime('%H:%M'))
                
                # Get data for each port
                for port in ports:
                    port_readings = (
                        PortPowerReading.query
                        .filter(PortPowerReading.port_id == port.id,
                               PortPowerReading.timestamp >= start_time,
                               PortPowerReading.timestamp <= end_time)
                        .all()
                    )
                    
                    # Group by 15-minute intervals
                    interval_data = {}
                    for reading in port_readings:
                        minutes = reading.timestamp.minute
                        rounded_minutes = (minutes // 15) * 15
                        interval = reading.timestamp.replace(minute=rounded_minutes, second=0, microsecond=0)
                        
                        if interval not in interval_data:
                            interval_data[interval] = []
                        interval_data[interval].append(reading.power_watts)
                    
                    # Create power data for this port
                    port_power_data = []
                    for i in range(96):
                        target_interval = start_time + timedelta(minutes=15*i)
                        if target_interval in interval_data:
                            avg_power = sum(interval_data[target_interval]) / len(interval_data[target_interval])
                            port_power_data.append(round(avg_power, 1))
                        else:
                            port_power_data.append(0)
                    
                    chart_data['ports'].append({
                        'id': port.id,
                        'name': port.name,
                        'port_number': port.port_number,
                        'power_watts': port_power_data
                    })
            
            elif period == 'week':
                # Get last 7 days of data for each port
                start_time = datetime.utcnow() - timedelta(days=7)
                
                chart_data = {
                    'labels': [],
                    'ports': []
                }
                
                # Create all 7 days
                for i in range(7):
                    target_date = datetime.utcnow() - timedelta(days=6-i)
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                
                # Get data for each port
                for port in ports:
                    port_readings = (
                        PortPowerReading.query
                        .filter(PortPowerReading.port_id == port.id,
                               PortPowerReading.timestamp >= start_time)
                        .all()
                    )
                    
                    # Group by day
                    daily_data = {}
                    for reading in port_readings:
                        day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                        if day not in daily_data:
                            daily_data[day] = []
                        daily_data[day].append(reading.power_watts)
                    
                    # Create power data for this port
                    port_power_data = []
                    for i in range(7):
                        target_date = datetime.utcnow() - timedelta(days=6-i)
                        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                        if target_date in daily_data:
                            avg_power = sum(daily_data[target_date]) / len(daily_data[target_date])
                            port_power_data.append(round(avg_power, 1))
                        else:
                            port_power_data.append(0)
                    
                    chart_data['ports'].append({
                        'id': port.id,
                        'name': port.name,
                        'port_number': port.port_number,
                        'power_watts': port_power_data
                    })
            
            elif period == 'month':
                # Get last 30 days of data for each port
                start_time = datetime.utcnow() - timedelta(days=30)
                
                chart_data = {
                    'labels': [],
                    'ports': []
                }
                
                # Create all 30 days
                for i in range(30):
                    target_date = datetime.utcnow() - timedelta(days=29-i)
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                
                # Get data for each port
                for port in ports:
                    port_readings = (
                        PortPowerReading.query
                        .filter(PortPowerReading.port_id == port.id,
                               PortPowerReading.timestamp >= start_time)
                        .all()
                    )
                    
                    # Group by day
                    daily_data = {}
                    for reading in port_readings:
                        day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                        if day not in daily_data:
                            daily_data[day] = []
                        daily_data[day].append(reading.power_watts)
                    
                    # Create power data for this port
                    port_power_data = []
                    for i in range(30):
                        target_date = datetime.utcnow() - timedelta(days=29-i)
                        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                        if target_date in daily_data:
                            avg_power = sum(daily_data[target_date]) / len(daily_data[target_date])
                            port_power_data.append(round(avg_power, 1))
                        else:
                            port_power_data.append(0)
                    
                    chart_data['ports'].append({
                        'id': port.id,
                        'name': port.name,
                        'port_number': port.port_number,
                        'power_watts': port_power_data
                    })
            
            elif period == 'year':
                # Get last 12 months of data for each port
                start_time = datetime.utcnow() - timedelta(days=365)
                
                chart_data = {
                    'labels': [],
                    'ports': []
                }
                
                # Create all 12 months
                for i in range(12):
                    target_month = datetime.utcnow() - timedelta(days=365-30*i)
                    target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_month.strftime('%Y-%m'))
                
                # Get data for each port
                for port in ports:
                    port_readings = (
                        PortPowerReading.query
                        .filter(PortPowerReading.port_id == port.id,
                               PortPowerReading.timestamp >= start_time)
                        .all()
                    )
                    
                    # Group by month
                    monthly_data = {}
                    for reading in port_readings:
                        month = reading.timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        if month not in monthly_data:
                            monthly_data[month] = []
                        monthly_data[month].append(reading.power_watts)
                    
                    # Create power data for this port
                    port_power_data = []
                    for i in range(12):
                        target_month = datetime.utcnow() - timedelta(days=365-30*i)
                        target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        if target_month in monthly_data:
                            avg_power = sum(monthly_data[target_month]) / len(monthly_data[target_month])
                            port_power_data.append(round(avg_power, 1))
                        else:
                            port_power_data.append(0)
                    
                    chart_data['ports'].append({
                        'id': port.id,
                        'name': port.name,
                        'port_number': port.port_number,
                        'power_watts': port_power_data
                    })
            
            return jsonify({
                'success': True,
                'data': chart_data,
                'period': period,
                'view_type': view_type
            })
        
    except Exception as e:
        logger.error(f"Error getting power data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ports')
def get_ports():
    """API endpoint to get list of ports"""
    try:
        pdu = PDU.query.first()
        if not pdu:
            return jsonify({'success': False, 'error': 'No PDU configured'}), 404
        
        ports = PDUPort.query.filter_by(pdu_id=pdu.id, is_active=True).order_by(PDUPort.port_number).all()
        port_list = []
        
        for port in ports:
            latest = PortPowerReading.query.filter_by(port_id=port.id).order_by(PortPowerReading.timestamp.desc()).first()
            port_data = {
                'id': port.id,
                'port_number': port.port_number,
                'name': port.name,
                'description': port.description,
                'is_active': port.is_active,
                'current_power_watts': latest.power_watts if latest else 0,
                'current_power_kw': latest.power_kw if latest else 0,
                'current_amps': latest.current_amps if latest else 0,
                'voltage': latest.voltage if latest else 0,
                'power_factor': latest.power_factor if latest else 0,
                'last_reading': latest.timestamp.isoformat() if latest else None
            }
            port_list.append(port_data)
        
        return jsonify({
            'success': True,
            'data': port_list
        })
        
    except Exception as e:
        logger.error(f"Error getting ports: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/update-port-name', methods=['POST'])
def update_port_name():
    """API endpoint to update port name"""
    try:
        data = request.get_json()
        port_id = data.get('port_id')
        new_name = data.get('name')
        
        if not port_id or not new_name:
            return jsonify({'success': False, 'error': 'Missing port_id or name'}), 400
        
        port = PDUPort.query.get(port_id)
        if not port:
            return jsonify({'success': False, 'error': 'Port not found'}), 404
        
        port.name = new_name
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Port {port.port_number} renamed to "{new_name}"'
        })
        
    except Exception as e:
        logger.error(f"Error updating port name: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/energy-data')
def get_energy_data():
    """API endpoint to get energy consumption data"""
    try:
        period = request.args.get('period', 'day')
        view_type = request.args.get('view', 'total')  # 'total' or 'ports'
        
        pdu = PDU.query.first()
        if not pdu:
            return jsonify({'success': False, 'error': 'No PDU configured'}), 404
        
        if view_type == 'total':
            # Get total PDU energy data
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
                    hourly_data[hour].append(reading.total_power_kw)
                
                chart_data = {
                    'labels': [],
                    'energy_kwh': []
                }
                
                # Create all 24 hours for today
                for i in range(24):
                    target_hour = today_start + timedelta(hours=i)
                    chart_data['labels'].append(target_hour.strftime('%H'))
                    
                    if target_hour in hourly_data:
                        energy_kwh = sum(hourly_data[target_hour]) / 60
                        chart_data['energy_kwh'].append(round(energy_kwh, 3))
                    else:
                        chart_data['energy_kwh'].append(0)
            
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
                    daily_data[day].append(reading.total_power_kw)
                
                chart_data = {
                    'labels': [],
                    'energy_kwh': []
                }
                
                # Create all 7 days
                for i in range(7):
                    target_date = datetime.utcnow() - timedelta(days=6-i)
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                    
                    if target_date in daily_data:
                        energy_kwh = sum(daily_data[target_date]) / 60
                        chart_data['energy_kwh'].append(round(energy_kwh, 3))
                    else:
                        chart_data['energy_kwh'].append(0)
            
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
                    daily_data[day].append(reading.total_power_kw)
                
                chart_data = {
                    'labels': [],
                    'energy_kwh': []
                }
                
                # Create all 30 days
                for i in range(30):
                    target_date = datetime.utcnow() - timedelta(days=29-i)
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                    
                    if target_date in daily_data:
                        energy_kwh = sum(daily_data[target_date]) / 60
                        chart_data['energy_kwh'].append(round(energy_kwh, 3))
                    else:
                        chart_data['energy_kwh'].append(0)
            
            elif period == 'year':
                # Get monthly energy consumption for the last 12 months
                year_start = datetime.utcnow() - timedelta(days=365)
                readings = PowerReading.query.filter(PowerReading.timestamp >= year_start).all()
                
                # Group by month
                monthly_data = {}
                for reading in readings:
                    month = reading.timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    if month not in monthly_data:
                        monthly_data[month] = []
                    monthly_data[month].append(reading.total_power_kw)
                
                chart_data = {
                    'labels': [],
                    'energy_kwh': []
                }
                
                # Create all 12 months
                for i in range(12):
                    target_month = datetime.utcnow() - timedelta(days=365-30*i)
                    target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    chart_data['labels'].append(target_month.strftime('%Y-%m'))
                    
                    if target_month in monthly_data:
                        energy_kwh = sum(monthly_data[target_month]) / 60
                        chart_data['energy_kwh'].append(round(energy_kwh, 3))
                    else:
                        chart_data['energy_kwh'].append(0)
            
            return jsonify({
                'success': True,
                'data': chart_data,
                'period': period,
                'view_type': view_type
            })
        
        else:
            # Get individual port energy data (similar structure to power data)
            # This would be implemented similarly to the power data endpoint
            return jsonify({
                'success': False,
                'error': 'Port energy data not yet implemented'
            }), 501
        
    except Exception as e:
        logger.error(f"Error getting energy data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/groups')
def get_groups():
    """API endpoint to get all outlet groups"""
    try:
        groups = OutletGroup.query.order_by(OutletGroup.name).all()
        group_list = []
        
        for group in groups:
            group_data = {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'outlet_ids': group.get_outlet_ids(),
                'color': group.color,
                'created_at': group.created_at.isoformat(),
                'updated_at': group.updated_at.isoformat()
            }
            group_list.append(group_data)
        
        return jsonify({
            'success': True,
            'data': group_list
        })
        
    except Exception as e:
        logger.error(f"Error getting groups: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/groups', methods=['POST'])
def create_group():
    """API endpoint to create a new outlet group"""
    try:
        data = request.get_json()
        password = data.get('password')
        
        if password != GROUP_MANAGEMENT_PASSWORD:
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
        
        name = data.get('name')
        description = data.get('description', '')
        outlet_ids = data.get('outlet_ids', [])
        color = data.get('color', '#6366f1')
        
        if not name:
            return jsonify({'success': False, 'error': 'Group name is required'}), 400
        
        # Check if group name already exists
        existing_group = OutletGroup.query.filter_by(name=name).first()
        if existing_group:
            return jsonify({'success': False, 'error': 'Group name already exists'}), 400
        
        group = OutletGroup(
            name=name,
            description=description,
            color=color
        )
        group.set_outlet_ids(outlet_ids)
        
        db.session.add(group)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Group "{name}" created successfully',
            'data': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'outlet_ids': group.get_outlet_ids(),
                'color': group.color
            }
        })
        
    except Exception as e:
        logger.error(f"Error creating group: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/groups/<int:group_id>', methods=['PUT'])
def update_group(group_id):
    """API endpoint to update an outlet group"""
    try:
        data = request.get_json()
        password = data.get('password')
        
        if password != GROUP_MANAGEMENT_PASSWORD:
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
        
        group = OutletGroup.query.get(group_id)
        if not group:
            return jsonify({'success': False, 'error': 'Group not found'}), 404
        
        name = data.get('name')
        description = data.get('description')
        outlet_ids = data.get('outlet_ids')
        color = data.get('color')
        
        if name and name != group.name:
            # Check if new name already exists
            existing_group = OutletGroup.query.filter_by(name=name).first()
            if existing_group and existing_group.id != group_id:
                return jsonify({'success': False, 'error': 'Group name already exists'}), 400
            group.name = name
        
        if description is not None:
            group.description = description
        
        if outlet_ids is not None:
            group.set_outlet_ids(outlet_ids)
        
        if color is not None:
            group.color = color
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Group "{group.name}" updated successfully',
            'data': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'outlet_ids': group.get_outlet_ids(),
                'color': group.color
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating group: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
def delete_group(group_id):
    """API endpoint to delete an outlet group"""
    try:
        data = request.get_json()
        password = data.get('password')
        
        if password != GROUP_MANAGEMENT_PASSWORD:
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
        
        group = OutletGroup.query.get(group_id)
        if not group:
            return jsonify({'success': False, 'error': 'Group not found'}), 404
        
        group_name = group.name
        db.session.delete(group)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Group "{group_name}" deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting group: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/group-power-data')
def get_group_power_data():
    """API endpoint to get power consumption data for groups"""
    try:
        period = request.args.get('period', 'hour')
        group_ids = request.args.getlist('group_ids')  # List of group IDs
        
        pdu = PDU.query.first()
        if not pdu:
            return jsonify({'success': False, 'error': 'No PDU configured'}), 404
        
        if not group_ids:
            return jsonify({'success': False, 'error': 'No groups specified'}), 400
        
        # Get groups
        groups = OutletGroup.query.filter(OutletGroup.id.in_(group_ids)).all()
        if not groups:
            return jsonify({'success': False, 'error': 'No valid groups found'}), 404
        
        # Calculate time range based on period
        now_utc = datetime.utcnow()
        if period == 'hour':
            end_time = now_utc.replace(minute=(now_utc.minute // 15) * 15, second=0, microsecond=0)
            start_time = end_time - timedelta(hours=24)
        elif period == 'week':
            start_time = now_utc - timedelta(days=7)
            end_time = now_utc
        elif period == 'month':
            start_time = now_utc - timedelta(days=30)
            end_time = now_utc
        elif period == 'year':
            start_time = now_utc - timedelta(days=365)
            end_time = now_utc
        else:
            start_time = now_utc - timedelta(hours=24)
            end_time = now_utc
        
        chart_data = {
            'labels': [],
            'groups': []
        }
        
        # Create time labels
        if period == 'hour':
            for i in range(96):  # 24 hours * 4 intervals per hour
                target_interval = start_time + timedelta(minutes=15*i)
                uk_time = target_interval.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/London'))
                chart_data['labels'].append(uk_time.strftime('%H:%M'))
        elif period in ['week', 'month']:
            for i in range(7 if period == 'week' else 30):
                target_date = now_utc - timedelta(days=(6-i) if period == 'week' else (29-i))
                target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
        elif period == 'year':
            for i in range(12):
                target_month = now_utc - timedelta(days=365-30*i)
                target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(target_month.strftime('%Y-%m'))
        
        # Calculate power for each group
        for group in groups:
            outlet_ids = group.get_outlet_ids()
            if not outlet_ids:
                continue
            
            # Get ports for this group
            ports = PDUPort.query.filter(PDUPort.id.in_(outlet_ids)).all()
            if not ports:
                continue
            
            group_power_data = []
            
            if period == 'hour':
                # 15-minute intervals
                for i in range(96):
                    target_interval = start_time + timedelta(minutes=15*i)
                    
                    # Get readings for this interval
                    total_power = 0
                    for port in ports:
                        readings = PortPowerReading.query.filter(
                            PortPowerReading.port_id == port.id,
                            PortPowerReading.timestamp >= target_interval,
                            PortPowerReading.timestamp < target_interval + timedelta(minutes=15)
                        ).all()
                        
                        if readings:
                            avg_power = sum(r.power_watts for r in readings) / len(readings)
                            total_power += avg_power
                    
                    group_power_data.append(round(total_power, 1))
            
            elif period in ['week', 'month']:
                # Daily intervals
                for i in range(7 if period == 'week' else 30):
                    target_date = now_utc - timedelta(days=(6-i) if period == 'week' else (29-i))
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    next_date = target_date + timedelta(days=1)
                    
                    total_power = 0
                    for port in ports:
                        readings = PortPowerReading.query.filter(
                            PortPowerReading.port_id == port.id,
                            PortPowerReading.timestamp >= target_date,
                            PortPowerReading.timestamp < next_date
                        ).all()
                        
                        if readings:
                            avg_power = sum(r.power_watts for r in readings) / len(readings)
                            total_power += avg_power
                    
                    group_power_data.append(round(total_power, 1))
            
            elif period == 'year':
                # Monthly intervals
                for i in range(12):
                    target_month = now_utc - timedelta(days=365-30*i)
                    target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    next_month = target_month + timedelta(days=30)
                    
                    total_power = 0
                    for port in ports:
                        readings = PortPowerReading.query.filter(
                            PortPowerReading.port_id == port.id,
                            PortPowerReading.timestamp >= target_month,
                            PortPowerReading.timestamp < next_month
                        ).all()
                        
                        if readings:
                            avg_power = sum(r.power_watts for r in readings) / len(readings)
                            total_power += avg_power
                    
                    group_power_data.append(round(total_power, 1))
            
            chart_data['groups'].append({
                'id': group.id,
                'name': group.name,
                'color': group.color,
                'power_watts': group_power_data
            })
        
        return jsonify({
            'success': True,
            'data': chart_data,
            'period': period
        })
        
    except Exception as e:
        logger.error(f"Error getting group power data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/custom-power-data')
def get_custom_power_data():
    """API endpoint to get power consumption data for custom outlet selection"""
    try:
        period = request.args.get('period', 'hour')
        outlet_ids = request.args.getlist('outlet_ids')  # List of outlet IDs
        
        pdu = PDU.query.first()
        if not pdu:
            return jsonify({'success': False, 'error': 'No PDU configured'}), 404
        
        if not outlet_ids:
            return jsonify({'success': False, 'error': 'No outlets specified'}), 400
        
        # Get ports
        ports = PDUPort.query.filter(PDUPort.id.in_(outlet_ids)).all()
        if not ports:
            return jsonify({'success': False, 'error': 'No valid outlets found'}), 404
        
        # Calculate time range based on period
        now_utc = datetime.utcnow()
        if period == 'hour':
            end_time = now_utc.replace(minute=(now_utc.minute // 15) * 15, second=0, microsecond=0)
            start_time = end_time - timedelta(hours=24)
        elif period == 'week':
            start_time = now_utc - timedelta(days=7)
            end_time = now_utc
        elif period == 'month':
            start_time = now_utc - timedelta(days=30)
            end_time = now_utc
        elif period == 'year':
            start_time = now_utc - timedelta(days=365)
            end_time = now_utc
        else:
            start_time = now_utc - timedelta(hours=24)
            end_time = now_utc
        
        chart_data = {
            'labels': [],
            'outlets': []
        }
        
        # Create time labels (same logic as group power data)
        if period == 'hour':
            for i in range(96):
                target_interval = start_time + timedelta(minutes=15*i)
                uk_time = target_interval.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/London'))
                chart_data['labels'].append(uk_time.strftime('%H:%M'))
        elif period in ['week', 'month']:
            for i in range(7 if period == 'week' else 30):
                target_date = now_utc - timedelta(days=(6-i) if period == 'week' else (29-i))
                target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
        elif period == 'year':
            for i in range(12):
                target_month = now_utc - timedelta(days=365-30*i)
                target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(target_month.strftime('%Y-%m'))
        
        # Calculate power for each outlet
        for port in ports:
            outlet_power_data = []
            
            if period == 'hour':
                for i in range(96):
                    target_interval = start_time + timedelta(minutes=15*i)
                    
                    readings = PortPowerReading.query.filter(
                        PortPowerReading.port_id == port.id,
                        PortPowerReading.timestamp >= target_interval,
                        PortPowerReading.timestamp < target_interval + timedelta(minutes=15)
                    ).all()
                    
                    if readings:
                        avg_power = sum(r.power_watts for r in readings) / len(readings)
                        outlet_power_data.append(round(avg_power, 1))
                    else:
                        outlet_power_data.append(0)
            
            elif period in ['week', 'month']:
                for i in range(7 if period == 'week' else 30):
                    target_date = now_utc - timedelta(days=(6-i) if period == 'week' else (29-i))
                    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    next_date = target_date + timedelta(days=1)
                    
                    readings = PortPowerReading.query.filter(
                        PortPowerReading.port_id == port.id,
                        PortPowerReading.timestamp >= target_date,
                        PortPowerReading.timestamp < next_date
                    ).all()
                    
                    if readings:
                        avg_power = sum(r.power_watts for r in readings) / len(readings)
                        outlet_power_data.append(round(avg_power, 1))
                    else:
                        outlet_power_data.append(0)
            
            elif period == 'year':
                for i in range(12):
                    target_month = now_utc - timedelta(days=365-30*i)
                    target_month = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    next_month = target_month + timedelta(days=30)
                    
                    readings = PortPowerReading.query.filter(
                        PortPowerReading.port_id == port.id,
                        PortPowerReading.timestamp >= target_month,
                        PortPowerReading.timestamp < next_month
                    ).all()
                    
                    if readings:
                        avg_power = sum(r.power_watts for r in readings) / len(readings)
                        outlet_power_data.append(round(avg_power, 1))
                    else:
                        outlet_power_data.append(0)
            
            chart_data['outlets'].append({
                'id': port.id,
                'name': port.name,
                'port_number': port.port_number,
                'power_watts': outlet_power_data
            })
        
        return jsonify({
            'success': True,
            'data': chart_data,
            'period': period
        })
        
    except Exception as e:
        logger.error(f"Error getting custom power data: {str(e)}")
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
            pdu = PDU.query.first()
            if not pdu:
                return jsonify({'success': False, 'error': 'No PDU configured'}), 404
            
            # Get power readings for the specified period
            if period == 'day':
                start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == 'week':
                start_time = datetime.utcnow() - timedelta(days=7)
            elif period == 'month':
                start_time = datetime.utcnow() - timedelta(days=30)
            else:
                start_time = datetime.utcnow() - timedelta(days=1)
            
            # Get total PDU readings
            total_readings = PowerReading.query.filter(PowerReading.timestamp >= start_time).order_by(PowerReading.timestamp).all()
            
            # Get port readings
            ports = PDUPort.query.filter_by(pdu_id=pdu.id, is_active=True).order_by(PDUPort.port_number).all()
            port_readings = {}
            for port in ports:
                readings = PortPowerReading.query.filter(
                    PortPowerReading.port_id == port.id,
                    PortPowerReading.timestamp >= start_time
                ).order_by(PortPowerReading.timestamp).all()
                port_readings[port.id] = readings
            
            # Create CSV content
            csv_content = "Timestamp,Total Power (Watts),Total Power (kW)"
            for port in ports:
                csv_content += f",{port.name} (Watts),{port.name} (kW)"
            csv_content += "\n"
            
            # Combine all timestamps and create rows
            all_timestamps = set()
            for reading in total_readings:
                all_timestamps.add(reading.timestamp)
            for port_id, readings in port_readings.items():
                for reading in readings:
                    all_timestamps.add(reading.timestamp)
            
            all_timestamps = sorted(list(all_timestamps))
            
            for timestamp in all_timestamps:
                # Find total reading for this timestamp
                total_reading = next((r for r in total_readings if r.timestamp == timestamp), None)
                total_watts = total_reading.total_power_watts if total_reading else 0
                total_kw = total_reading.total_power_kw if total_reading else 0
                
                csv_content += f"{timestamp},{total_watts},{total_kw}"
                
                # Add port readings for this timestamp
                for port in ports:
                    port_reading = next((r for r in port_readings[port.id] if r.timestamp == timestamp), None)
                    port_watts = port_reading.power_watts if port_reading else 0
                    port_kw = port_reading.power_kw if port_reading else 0
                    csv_content += f",{port_watts},{port_kw}"
                
                csv_content += "\n"
            
            from flask import Response
            return Response(
                csv_content,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=raritan-pdu-data-{period}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv'}
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

