#!/usr/bin/env python3
"""
PDU Power Monitoring Web Application
Flask-based web interface for monitoring APC PDU power consumption
"""

from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import logging
import requests

from config import DATABASE_URI, FLASK_HOST, FLASK_PORT, FLASK_DEBUG, ALERT_CONFIG
from sqlalchemy import func

# Discord webhook configuration
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1411794302513975499/fSvpOKKmWExxqOpSf7vDg5fJhkUMnlgQkeuaF3qpQwnI6vVC1POk3xw3yS175Ss3m0XB"
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

# Alert state tracking to prevent duplicate alerts
alert_states = {}  # Track which alerts are currently active
sustained_power_tracking = {}  # Track sustained high power periods
cleared_alerts = set()  # Track alerts that have been permanently cleared

def check_sustained_high_power(pdu_id, pdu_name, current_power, threshold_watts=None, duration_minutes=None):
    """Check if power has been high for a sustained period"""
    if threshold_watts is None:
        threshold_watts = ALERT_CONFIG['high_power_threshold_watts']
    if duration_minutes is None:
        duration_minutes = ALERT_CONFIG['high_power_duration_minutes']
    
    current_time = datetime.utcnow()
    
    # Initialize tracking for this PDU if not exists
    if pdu_id not in sustained_power_tracking:
        sustained_power_tracking[pdu_id] = {
            'start_time': None,
            'threshold_exceeded': False,
            'last_check': current_time
        }
    
    tracking = sustained_power_tracking[pdu_id]
    
    # Check if current power exceeds threshold
    if current_power > threshold_watts:
        if not tracking['threshold_exceeded']:
            # Just started exceeding threshold
            tracking['start_time'] = current_time
            tracking['threshold_exceeded'] = True
            logger.info(f"🔍 {pdu_name} power threshold exceeded: {current_power:.1f}W > {threshold_watts}W")
        
        # Check if we've been over threshold for the required duration
        if tracking['start_time']:
            duration_exceeded = (current_time - tracking['start_time']).total_seconds() / 60
            if duration_exceeded >= duration_minutes:
                logger.warning(f"🚨 {pdu_name} sustained high power for {duration_exceeded:.1f} minutes: {current_power:.1f}W")
                return True, duration_exceeded
    else:
        # Power is back below threshold, reset tracking
        if tracking['threshold_exceeded']:
            logger.info(f"✅ {pdu_name} power back to normal: {current_power:.1f}W")
        tracking['threshold_exceeded'] = False
        tracking['start_time'] = None
    
    return False, 0

def send_discord_alert(alert):
    """Send alert to Discord webhook"""
    try:
        # Determine color based on severity
        color_map = {
            'high': 0xFF0000,    # Red
            'medium': 0xFFA500,  # Orange
            'low': 0x0000FF      # Blue
        }
        color = color_map.get(alert['severity'], 0x808080)  # Default gray
        
        # Determine emoji based on alert type
        emoji_map = {
            'offline': '🔴',
            'high_power': '⚡',
            'zero_power': '🔌',
            'power_spike': '📈',
            'low_efficiency': '📉',
            'sustained_high': '🔥'
        }
        emoji = emoji_map.get(alert['type'], '⚠️')
        
        embed = {
            "title": f"{emoji} PDU Alert: {alert['type'].replace('_', ' ').title()}",
            "description": alert['message'],
            "color": color,
            "timestamp": alert['timestamp'],
            "footer": {
                "text": "PDU Power Monitoring System"
            }
        }
        
        payload = {
            "embeds": [embed]
        }
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            logger.info(f"Discord alert sent successfully: {alert['type']}")
        else:
            logger.error(f"Failed to send Discord alert: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error sending Discord alert: {str(e)}")

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
        period = request.args.get('period', 'hour')
        
        # Get power data directly from database
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
                # Round to nearest 15-minute interval
                minutes = reading.timestamp.minute
                rounded_minutes = (minutes // 15) * 15
                interval = reading.timestamp.replace(minute=rounded_minutes, second=0, microsecond=0)
                
                if interval not in interval_data:
                    interval_data[interval] = []
                interval_data[interval].append(reading.power_watts)
            
            chart_data = {
                'labels': [],
                'power_watts': []
            }
            
            # Create all 15-minute intervals for the last 24 hours
            for i in range(96):  # 24 hours * 4 intervals per hour
                target_interval = start_time + timedelta(minutes=15*i)
                # Convert UTC interval to UK time for labeling
                uk_time = target_interval.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Europe/London'))
                chart_data['labels'].append(uk_time.strftime('%H:%M'))
                
                if target_interval in interval_data:
                    avg_power = sum(interval_data[target_interval]) / len(interval_data[target_interval])
                    chart_data['power_watts'].append(round(avg_power, 1))
                else:
                    chart_data['power_watts'].append(0)  # Use 0 to show all dots
        
        elif period == 'day':
            # Get last 7 days of data, grouped by day
            start_time = datetime.utcnow() - timedelta(days=7)
            readings = PowerReading.query.filter(PowerReading.timestamp >= start_time).all()
            
            # Group by day
            daily_data = {}
            for reading in readings:
                day = reading.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                if day not in daily_data:
                    daily_data[day] = []
                daily_data[day].append(reading.power_watts)
            
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
        
        elif period == 'week':
            # Last 7 days, UK-local day boundaries, one dot per day
            uk_tz = ZoneInfo('Europe/London')
            now_uk = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(uk_tz)
            start_uk = (now_uk - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_utc = start_uk.astimezone(timezone.utc).replace(tzinfo=None)

            readings = PowerReading.query.filter(PowerReading.timestamp >= start_utc).all()

            # Group by UK-local day
            daily_data = {}
            for reading in readings:
                ts_uk = reading.timestamp.replace(tzinfo=timezone.utc).astimezone(uk_tz)
                day_key = ts_uk.replace(hour=0, minute=0, second=0, microsecond=0)
                if day_key not in daily_data:
                    daily_data[day_key] = []
                daily_data[day_key].append(reading.power_watts)

            chart_data = {
                'labels': [],
                'power_watts': []
            }

            for i in range(7):
                day_uk = start_uk + timedelta(days=i)
                day_uk_midnight = day_uk.replace(hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(day_uk_midnight.strftime('%Y-%m-%d'))
                if day_uk_midnight in daily_data:
                    avg_power = sum(daily_data[day_uk_midnight]) / len(daily_data[day_uk_midnight])
                    chart_data['power_watts'].append(round(avg_power, 1))
                else:
                    chart_data['power_watts'].append(0)
        
        elif period == 'month':
            # Last 30 days, UK-local day boundaries, one dot per day
            uk_tz = ZoneInfo('Europe/London')
            now_uk = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(uk_tz)
            start_uk = (now_uk - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_utc = start_uk.astimezone(timezone.utc).replace(tzinfo=None)

            readings = PowerReading.query.filter(PowerReading.timestamp >= start_utc).all()

            # Group by UK-local day
            daily_data = {}
            for reading in readings:
                ts_uk = reading.timestamp.replace(tzinfo=timezone.utc).astimezone(uk_tz)
                day_key = ts_uk.replace(hour=0, minute=0, second=0, microsecond=0)
                if day_key not in daily_data:
                    daily_data[day_key] = []
                daily_data[day_key].append(reading.power_watts)

            chart_data = {
                'labels': [],
                'power_watts': []
            }

            for i in range(30):
                day_uk = start_uk + timedelta(days=i)
                day_uk_midnight = day_uk.replace(hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(day_uk_midnight.strftime('%Y-%m-%d'))
                if day_uk_midnight in daily_data:
                    avg_power = sum(daily_data[day_uk_midnight]) / len(daily_data[day_uk_midnight])
                    chart_data['power_watts'].append(round(avg_power, 1))
                else:
                    chart_data['power_watts'].append(0)
        
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
        
        # Calculate energy consumption (kWh) from power readings
        # Each reading represents instantaneous power, so we need to integrate over time
        # Assuming readings are taken every minute, each reading contributes 1/60 kWh
        total_energy_kwh = sum(reading.power_kw for reading in today_readings) / 60.0  # Convert to kWh (assuming 1-minute intervals)
        
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
            
            chart_data = {
                'labels': [],
                'energy_kwh': []
            }
            
            # Create all 24 hours for today
            for i in range(24):
                target_hour = today_start + timedelta(hours=i)
                # Show hour labels (e.g., "9", "10", "11") for the x-axis
                chart_data['labels'].append(target_hour.strftime('%H'))
                
                if target_hour in hourly_data:
                    # Sum power readings and convert to kWh (assuming 1-minute intervals)
                    energy_kwh = sum(hourly_data[target_hour]) / 60
                    chart_data['energy_kwh'].append(round(energy_kwh, 3))
                else:
                    chart_data['energy_kwh'].append(0)  # Use 0 to show all bars
        
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
            
            # Create all 7 days
            for i in range(7):
                target_date = datetime.utcnow() - timedelta(days=6-i)
                target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                
                if target_date in daily_data:
                    energy_kwh = sum(daily_data[target_date]) / 60
                    chart_data['energy_kwh'].append(round(energy_kwh, 3))
                else:
                    chart_data['energy_kwh'].append(0)  # Use 0 to show all bars
        
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
            
            # Create all 30 days
            for i in range(30):
                target_date = datetime.utcnow() - timedelta(days=29-i)
                target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                chart_data['labels'].append(target_date.strftime('%Y-%m-%d'))
                
                if target_date in daily_data:
                    energy_kwh = sum(daily_data[target_date]) / 60
                    chart_data['energy_kwh'].append(round(energy_kwh, 3))
                else:
                    chart_data['energy_kwh'].append(0)  # Use 0 to show all bars
        
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
                headers={'Content-Disposition': f'attachment; filename=pdu-power-data-{period}-{datetime.now().strftime("%Y%m%d-%H%M%S")}.csv'}
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

@app.route('/api/alerts')
def get_alerts():
    """API endpoint to get current alerts"""
    try:
        # Get all PDUs
        pdus = PDU.query.all()
        alerts = []
        
        for pdu in pdus:
            latest = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
            
            if latest:
                # Check for various alert conditions
                time_diff = datetime.utcnow() - latest.timestamp
                
                # Offline alert (no reading in last X minutes)
                if time_diff.total_seconds() > ALERT_CONFIG['offline_timeout_minutes'] * 60:
                    alerts.append({
                        'type': 'offline',
                        'severity': 'high',
                        'message': f'{pdu.name} is offline (last reading: {time_diff.total_seconds()/60:.1f} minutes ago)',
                        'pdu_id': pdu.id,
                        'timestamp': latest.timestamp.isoformat()
                    })
                
                # Sustained high power alert (over threshold for sustained period)
                sustained_high, duration = check_sustained_high_power(
                    pdu.id, 
                    pdu.name, 
                    latest.power_watts
                )
                
                if sustained_high:
                    alerts.append({
                        'type': 'sustained_high_power',
                        'severity': 'medium',
                        'message': f'{pdu.name} sustained high power: {latest.power_watts:.1f}W for {duration:.1f} minutes',
                        'pdu_id': pdu.id,
                        'timestamp': latest.timestamp.isoformat(),
                        'duration_minutes': duration
                    })
                
                # Zero power alert (for any PDU showing 0W for sustained period)
                if latest.power_watts == 0:
                    # Check if this is a sustained zero reading
                    recent_readings = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).limit(ALERT_CONFIG['zero_power_sustained_readings'] + 1).all()
                    if len(recent_readings) >= ALERT_CONFIG['zero_power_sustained_readings']:
                        # Check if last few readings are also zero
                        if all(r.power_watts == 0 for r in recent_readings[:ALERT_CONFIG['zero_power_sustained_readings']]):
                            alerts.append({
                                'type': 'sustained_zero_power',
                                'severity': 'medium',
                                'message': f'{pdu.name} shows sustained zero power consumption',
                                'pdu_id': pdu.id,
                                'timestamp': latest.timestamp.isoformat()
                            })
                
                # Power spike alert (check for sustained increase)
                recent_readings = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).limit(5).all()
                if len(recent_readings) >= 3:
                    current_power = recent_readings[0].power_watts
                    previous_power = recent_readings[1].power_watts
                    if previous_power > 0:
                        power_increase = ((current_power - previous_power) / previous_power) * 100
                        if power_increase > ALERT_CONFIG['power_spike_threshold_percent']:
                            # Check if this spike is sustained (not just a momentary blip)
                            sustained_spike = True
                            for i in range(1, min(3, len(recent_readings))):
                                if recent_readings[i].power_watts > 0:
                                    spike_increase = ((recent_readings[i-1].power_watts - recent_readings[i].power_watts) / recent_readings[i].power_watts) * 100
                                    if spike_increase < ALERT_CONFIG['power_spike_sustained_threshold']:
                                        sustained_spike = False
                                        break
                            
                            if sustained_spike:
                                alerts.append({
                                    'type': 'sustained_power_spike',
                                    'severity': 'medium',
                                    'message': f'{pdu.name} sustained power spike: {power_increase:.1f}% increase ({previous_power:.1f}W → {current_power:.1f}W)',
                                    'pdu_id': pdu.id,
                                    'timestamp': latest.timestamp.isoformat()
                                })
                
                # Efficiency alert (low power factor)
                estimated_power_factor = 0.95  # Default assumption
                if latest.power_watts > 0:
                    # Calculate apparent power (V * I)
                    apparent_power = 240 * (latest.power_watts / 240 / 0.95)  # Reverse calculate current
                    if apparent_power > 0:
                        estimated_power_factor = latest.power_watts / apparent_power
                        if estimated_power_factor < ALERT_CONFIG['low_efficiency_threshold']:
                            alerts.append({
                                'type': 'low_efficiency',
                                'severity': 'low',
                                'message': f'{pdu.name} low power factor: {estimated_power_factor:.2f} (should be >{ALERT_CONFIG["low_efficiency_threshold"]})',
                                'pdu_id': pdu.id,
                                'timestamp': latest.timestamp.isoformat()
                            })
                
                # Trend alert (sustained high usage >80% of typical for 1 hour)
                # Get readings from last hour
                hour_ago = datetime.utcnow() - timedelta(hours=1)
                hourly_readings = PowerReading.query.filter(
                    PowerReading.pdu_id == pdu.id,
                    PowerReading.timestamp >= hour_ago
                ).all()
                
                if len(hourly_readings) >= 10:  # At least 10 readings in the hour
                    avg_power = sum(r.power_watts for r in hourly_readings) / len(hourly_readings)
                    # Assume typical usage is around 1000W (adjust as needed)
                    typical_usage = 1000
                    if avg_power > typical_usage * 0.8:  # 80% of 1000W = 800W threshold
                        alerts.append({
                            'type': 'sustained_high',
                            'severity': 'medium',
                            'message': f'{pdu.name} sustained high usage: {avg_power:.1f}W average over 1 hour',
                            'pdu_id': pdu.id,
                            'timestamp': latest.timestamp.isoformat()
                        })
        
        # Send Discord notifications for new alerts only
        for alert in alerts:
            # Create a unique key for this alert
            alert_key = f"{alert['pdu_id']}_{alert['type']}"
            
            # Check if this alert has been permanently cleared
            if alert_key in cleared_alerts:
                continue  # Skip this alert entirely - it's been permanently cleared
            
            # Check if this alert is new
            if alert_key not in alert_states:
                # This is a new alert, send Discord notification
                send_discord_alert(alert)
                alert_states[alert_key] = {
                    'timestamp': alert['timestamp'],
                    'message': alert['message']
                }
            else:
                # Update existing alert timestamp
                alert_states[alert_key]['timestamp'] = alert['timestamp']
        
        # Clean up resolved alerts from state tracking
        current_alert_keys = {f"{alert['pdu_id']}_{alert['type']}" for alert in alerts}
        resolved_keys = set(alert_states.keys()) - current_alert_keys
        for key in resolved_keys:
            del alert_states[key]
        
        # Filter out permanently cleared alerts from the final result
        filtered_alerts = []
        for alert in alerts:
            alert_key = f"{alert['pdu_id']}_{alert['type']}"
            if alert_key not in cleared_alerts:
                filtered_alerts.append(alert)
        
        return jsonify({
            'success': True,
            'alerts': filtered_alerts,
            'count': len(filtered_alerts)
        })
        
    except Exception as e:
        logger.error(f"Error getting alerts: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/clear-high-usage-alerts', methods=['POST'])
def clear_high_usage_alerts():
    """Clear high usage alerts by resetting the sustained power tracking and marking as permanently cleared"""
    try:
        global sustained_power_tracking, cleared_alerts
        
        # Get the request data to see what type of alerts to clear
        data = request.get_json() or {}
        alert_types = data.get('alert_types', ['sustained_high_power', 'sustained_high', 'power_spike'])
        
        # Clear all sustained power tracking data
        sustained_power_tracking.clear()
        
        # Mark specified alert types as permanently cleared
        # This will prevent them from appearing again even if conditions are met
        cleared_count = 0
        for alert_key in list(alert_states.keys()):
            if any(alert_type in alert_key for alert_type in alert_types):
                cleared_alerts.add(alert_key)
                del alert_states[alert_key]
                cleared_count += 1
        
        logger.info(f"Cleared {cleared_count} high usage alerts - sustained power tracking reset and alerts marked as permanently cleared")
        
        return jsonify({
            'success': True,
            'message': f'High usage alerts cleared successfully and will not reappear ({cleared_count} alerts cleared)'
        })
        
    except Exception as e:
        logger.error(f"Error clearing high usage alerts: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/power-summary')
def get_power_summary():
    """API endpoint to get detailed power summary"""
    try:
        # Get current readings
        pdus = PDU.query.all()
        summary = {
            'total_power_watts': 0,
            'total_power_kw': 0,
            'online_pdus': 0,
            'total_pdus': len(pdus),
            'pdus': []
        }
        
        for pdu in pdus:
            latest = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
            
            if latest:
                time_diff = datetime.utcnow() - latest.timestamp
                online = time_diff.total_seconds() < 300
                
                if online:
                    summary['total_power_watts'] += latest.power_watts
                    summary['total_power_kw'] += latest.power_kw
                    summary['online_pdus'] += 1
                
                summary['pdus'].append({
                    'id': pdu.id,
                    'name': pdu.name,
                    'ip_address': pdu.ip_address,
                    'online': online,
                    'current_power_watts': latest.power_watts,
                    'current_power_kw': latest.power_kw,
                    'last_reading': latest.timestamp.isoformat(),
                    'uptime_minutes': (datetime.utcnow() - latest.timestamp).total_seconds() / 60
                })
        
        # Calculate efficiency metrics
        if summary['online_pdus'] > 0:
            summary['avg_power_per_pdu'] = summary['total_power_watts'] / summary['online_pdus']
        else:
            summary['avg_power_per_pdu'] = 0
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Error getting power summary: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/debug-database')
def debug_database():
    """Debug endpoint to check database status"""
    try:
        # Get basic database info
        pdus = PDU.query.all()
        total_readings = PowerReading.query.count()
        
        # Get latest readings
        latest_readings = []
        for pdu in pdus:
            latest = PowerReading.query.filter_by(pdu_id=pdu.id).order_by(PowerReading.timestamp.desc()).first()
            if latest:
                latest_readings.append({
                    'pdu_name': pdu.name,
                    'pdu_ip': pdu.ip_address,
                    'latest_timestamp': latest.timestamp.isoformat(),
                    'latest_power_watts': latest.power_watts,
                    'time_diff_minutes': (datetime.utcnow() - latest.timestamp).total_seconds() / 60
                })
            else:
                latest_readings.append({
                    'pdu_name': pdu.name,
                    'pdu_ip': pdu.ip_address,
                    'latest_timestamp': None,
                    'latest_power_watts': None,
                    'time_diff_minutes': None
                })
        
        # Get reading count by time periods
        now = datetime.utcnow()
        last_hour = PowerReading.query.filter(PowerReading.timestamp >= now - timedelta(hours=1)).count()
        last_24h = PowerReading.query.filter(PowerReading.timestamp >= now - timedelta(hours=24)).count()
        last_7d = PowerReading.query.filter(PowerReading.timestamp >= now - timedelta(days=7)).count()
        
        # Get oldest and newest readings
        oldest = PowerReading.query.order_by(PowerReading.timestamp.asc()).first()
        newest = PowerReading.query.order_by(PowerReading.timestamp.desc()).first()
        
        # Get recent readings for debugging
        recent_readings = []
        if newest:
            recent_readings = PowerReading.query.order_by(PowerReading.timestamp.desc()).limit(10).all()
            recent_readings = [{
                'timestamp': r.timestamp.isoformat(),
                'pdu_id': r.pdu_id,
                'power_watts': r.power_watts
            } for r in recent_readings]
        
        debug_info = {
            'total_pdus': len(pdus),
            'total_readings': total_readings,
            'readings_last_hour': last_hour,
            'readings_last_24h': last_24h,
            'readings_last_7d': last_7d,
            'oldest_reading': oldest.timestamp.isoformat() if oldest else None,
            'newest_reading': newest.timestamp.isoformat() if newest else None,
            'pdu_status': latest_readings,
            'recent_readings': recent_readings,
            'current_time_utc': datetime.utcnow().isoformat()
        }
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
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

