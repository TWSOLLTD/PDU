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
import threading
import time
import hashlib
import os

from config import DATABASE_URI, FLASK_HOST, FLASK_PORT, FLASK_DEBUG, RARITAN_CONFIG, GROUP_MANAGEMENT_PASSWORD, DISCORD_WEBHOOK_URL
from models import db, PDU, PDUPort, PowerReading, PortPowerReading, PowerAggregation, SystemSettings, OutletGroup, init_db
from snmp_collector import collect_power_data
from discord_notifier import send_monthly_report, send_test_notification

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# In-memory cache for power data responses
power_data_cache = {}

# Cache TTL (seconds) per period
PERIOD_CACHE_TTLS = {
    'day-10min': 60,       # 1 minute
    'day': 60,             # 1 minute
    'week-10min': 300,     # 5 minutes
    'week': 300,           # 5 minutes
    'month': 600,          # 10 minutes
    'year-weekly': 600,    # 10 minutes
    'year-monthly': 600    # 10 minutes
}


def get_cache_ttl(period: str) -> int:
    """Return cache TTL in seconds for the given period."""
    return PERIOD_CACHE_TTLS.get(period, 0)


def make_cache_key(period: str, outlet_ids: list, user_timezone: str) -> tuple:
    """Construct cache key based on request parameters."""
    sorted_ids = tuple(sorted(outlet_ids))
    return (period, sorted_ids, user_timezone)


# Security check on startup
if not GROUP_MANAGEMENT_PASSWORD:
    logger.warning("⚠️  SECURITY WARNING: GROUP_MANAGEMENT_PASSWORD not set!")
    logger.warning("⚠️  Group management will be DISABLED until password is configured.")
    logger.warning("⚠️  Set GROUP_MANAGEMENT_PASSWORD in your .env file.")
else:
    logger.info("✅ Group management password configured securely")

# Check SNMP credentials
if not RARITAN_CONFIG['snmp_username'] or not RARITAN_CONFIG['snmp_auth_password'] or not RARITAN_CONFIG['snmp_priv_password']:
    logger.warning("⚠️  SECURITY WARNING: SNMP credentials not fully configured!")
    logger.warning("⚠️  Set SNMP_USERNAME, SNMP_AUTH_PASSWORD, SNMP_PRIV_PASSWORD in your .env file.")
else:
    logger.info("✅ SNMP credentials configured securely")

# Check Discord webhook
if not DISCORD_WEBHOOK_URL:
    logger.warning("⚠️  Discord webhook not configured!")
    logger.warning("⚠️  Set DISCORD_WEBHOOK_URL in your .env file.")
else:
    logger.info("✅ Discord webhook configured securely")

def verify_password(password):
    """Verify password securely"""
    # Get password from environment variable
    correct_password = GROUP_MANAGEMENT_PASSWORD
    
    # Security check: ensure password is actually set
    if not correct_password:
        logger.error("GROUP_MANAGEMENT_PASSWORD not set in environment variables!")
        return False
    
    # Security check: ensure provided password is not empty
    if not password or password.strip() == '':
        return False
    
    return password == correct_password


@app.route('/api/debug-password')
def debug_password():
    """Endpoint for frontend password verification"""
    try:
        password = request.args.get('password', '')
        
        if not password or password.strip() == '':
            return jsonify({
                'success': False,
                'error': 'Password cannot be empty',
                'data': {
                    'verification_result': False
                }
            }), 400
        
        verification_result = verify_password(password)
        
        if verification_result:
            return jsonify({
                'success': True,
                'data': {
                    'verification_result': True
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid password',
                'data': {
                    'verification_result': False
                }
            }), 401
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error verifying password',
            'data': {
                'verification_result': False
            }
        }), 500

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/power-data')
def get_power_data():
    """Get power data for charts with time period aggregation"""
    try:
        # Get query parameters
        period = request.args.get('period', 'day')
        outlet_ids = request.args.get('outlet_ids', '')
        
        # Parse outlet IDs
        if outlet_ids:
            outlet_ids = [int(id) for id in outlet_ids.split(',')]
        else:
            outlet_ids = []
        
        # Calculate time range and aggregation based on period
        import calendar
        from zoneinfo import ZoneInfo
        
        # Get user timezone from request headers (sent by frontend)
        user_timezone = request.headers.get('X-User-Timezone', 'Europe/London')
        cache_key = None
        cache_ttl = get_cache_ttl(period)

        if cache_ttl > 0:
            cache_key = make_cache_key(period, outlet_ids, user_timezone)
            cached_entry = power_data_cache.get(cache_key)
            if cached_entry and (time.time() - cached_entry['timestamp']) < cache_ttl:
                logger.info(f"Serving cached power data for key={cache_key}")
                return jsonify(cached_entry['payload'])
        
        # Convert UTC now to user's timezone for proper time range calculation
        utc_now = datetime.utcnow()
        user_tz = ZoneInfo(user_timezone)
        now = utc_now.replace(tzinfo=timezone.utc).astimezone(user_tz)
        
        if period == 'day':
            # Day hourly: 00:00 to 23:00 (24 hours)
            labels = [f"{i:02d}:00" for i in range(24)]
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Convert back to UTC for database queries
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 60
        elif period == 'day-10min':
            # Day 10-minute: 00:00 to 23:50 (144 intervals)
            labels = []
            for hour in range(24):
                for minute in range(0, 60, 10):
                    labels.append(f"{hour:02d}:{minute:02d}")
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 10
        elif period == 'week-10min':
            # Week 10-minute: Monday 00:00 to Sunday 23:50 (1008 intervals)
            labels = []
            days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            for day_idx in range(7):
                for hour in range(24):
                    for minute in range(0, 60, 10):
                        labels.append(f"{days[day_idx]} {hour:02d}:{minute:02d}")
            # Get start of current week (Monday)
            days_since_monday = now.weekday()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 10
        elif period == 'week':
            # Week daily: Monday to Sunday
            labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            # Get start of current week (Monday)
            days_since_monday = now.weekday()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 1440  # Daily
        elif period == 'month':
            # Month daily: 1st to last day of current month
            last_day = calendar.monthrange(now.year, now.month)[1]
            labels = [f"{day:02d}" for day in range(1, last_day + 1)]
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 1440  # Daily
        elif period == 'year-weekly':
            # Year weekly: Show date ranges for each week
            labels = []
            current_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Find the first Monday of the year
            while current_date.weekday() != 0:  # 0 = Monday
                current_date += timedelta(days=1)
            
            # Generate 52 weeks of date ranges
            for week in range(52):
                week_start = current_date + timedelta(weeks=week)
                week_end = week_start + timedelta(days=6)
                
                # Format: "Jan 6-12" (much shorter)
                start_day = week_start.day
                end_day = week_end.day
                month_name = week_start.strftime('%b')  # Short month name
                
                labels.append(f"{month_name} {start_day}-{end_day}")
            
            start_time = current_date
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 10080  # Weekly
        elif period == 'year-monthly':
            # Year monthly: January to December
            labels = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November', 'December']
            start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 43200  # Monthly
        else:
            # Default to day hourly
            labels = [f"{i:02d}:00" for i in range(24)]
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
            interval_minutes = 60
        
        # Get power data for selected outlets
        if outlet_ids:
            outlets_data = []
            for outlet_id in outlet_ids:
                outlet = PDUPort.query.get(outlet_id)
                if outlet:
                    # Get readings for this outlet
                    readings = PortPowerReading.query.filter(
                        PortPowerReading.port_id == outlet_id,
                        PortPowerReading.timestamp >= start_time_utc
                    ).order_by(PortPowerReading.timestamp).all()
                    
                    # Aggregate data by time intervals
                    power_values = []
                    energy_values = []
                    for i, label in enumerate(labels):
                        interval_start = start_time + timedelta(minutes=i * interval_minutes)
                        interval_end = interval_start + timedelta(minutes=interval_minutes)
                        
                        # Convert interval times to UTC for database comparison
                        interval_start_utc = interval_start.astimezone(timezone.utc).replace(tzinfo=None)
                        interval_end_utc = interval_end.astimezone(timezone.utc).replace(tzinfo=None)
                        
                        # Find readings in this interval
                        interval_readings = [
                            r for r in readings 
                            if interval_start_utc <= r.timestamp < interval_end_utc
                        ]
                        
                        if interval_readings:
                            # Calculate average power for this interval (for line graph)
                            avg_power = sum(r.power_watts for r in interval_readings) / len(interval_readings)
                            power_values.append(round(avg_power, 1))
                            
                            # Calculate actual energy consumption from minute-by-minute readings
                            total_energy_kwh = 0
                            for i in range(len(interval_readings) - 1):
                                # Calculate time difference between consecutive readings (in hours)
                                time_diff = (interval_readings[i + 1].timestamp - interval_readings[i].timestamp).total_seconds() / 3600
                                
                                # Energy = Power × Time (convert Watts to kWh)
                                energy_kwh = (interval_readings[i].power_watts * time_diff) / 1000
                                total_energy_kwh += energy_kwh
                            
                            # Add energy for the last reading (assume 1 minute duration)
                            if len(interval_readings) > 0:
                                last_energy = (interval_readings[-1].power_watts * (1/60)) / 1000  # 1 minute = 1/60 hours
                                total_energy_kwh += last_energy
                            
                            energy_values.append(round(total_energy_kwh, 3))
                        else:
                            power_values.append(0)  # Use 0 for missing data to show all time slots
                            energy_values.append(0)
                    
                    outlets_data.append({
                        'id': outlet.id,
                        'name': outlet.name,
                        'port_number': outlet.port_number,
                        'power_watts': power_values,  # For line graph (power over time)
                        'energy_kwh': energy_values  # For bar graph (energy consumption)
                    })
            
            response_payload = {
                'success': True,
                'data': {
                    'labels': labels,
                    'outlets': outlets_data
                },
                'period': period,
                'start_time': start_time.isoformat(),
                'end_time': now.isoformat(),
                'user_timezone': user_timezone
            }

            if cache_key:
                power_data_cache[cache_key] = {
                    'timestamp': time.time(),
                    'payload': response_payload
                }

            return jsonify(response_payload)
        else:
            # No outlets selected
            response_payload = {
                'success': True,
                'data': {
                    'labels': labels,
                    'outlets': []
                },
                'period': period,
                'start_time': start_time.isoformat(),
                'end_time': now.isoformat(),
                'user_timezone': user_timezone
            }

            if cache_key:
                power_data_cache[cache_key] = {
                    'timestamp': time.time(),
                    'payload': response_payload
                }

            return jsonify(response_payload)
        
    except Exception as e:
        logger.error(f"Error getting power data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/outlets')
def get_outlets():
    """Get all outlets with their current status"""
    try:
        outlets = PDUPort.query.filter_by(is_active=True).all()
        
        outlet_data = []
        for outlet in outlets:
            # Get latest power reading
            latest_reading = PortPowerReading.query.filter_by(
                port_id=outlet.id
            ).order_by(PortPowerReading.timestamp.desc()).first()
            
            # Get status from the latest reading (stored from SNMP)
            power_watts = latest_reading.power_watts if latest_reading else 0
            status = latest_reading.status if latest_reading and latest_reading.status else 'OFF'
            
            # Debug logging
            logger.info(f"Outlet {outlet.port_number}: name='{outlet.name}', status={status}, power={power_watts}W")
            
            outlet_data.append({
                'id': outlet.id,
                'name': outlet.name,
                'port_number': outlet.port_number,
                'description': outlet.description,
                'power_watts': power_watts,
                'status': status,
                'last_updated': latest_reading.timestamp.isoformat() if latest_reading else None
            })
        
        logger.info(f"API returning {len(outlet_data)} outlets")
        return jsonify({
            'success': True,
            'data': outlet_data
        })
        
    except Exception as e:
        logger.error(f"Error getting outlets: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/groups', methods=['GET', 'POST'])
def handle_groups():
    """Handle group operations"""
    if request.method == 'GET':
        # Get all groups
        try:
            groups = OutletGroup.query.all()
            group_data = []
            
            for group in groups:
                group_data.append({
                    'id': group.id,
                    'name': group.name,
                    'description': group.description,
                    'outlet_ids': group.get_outlet_ids(),
                    'color': group.color,
                    'created_at': group.created_at.isoformat(),
                    'updated_at': group.updated_at.isoformat()
                })
            
            return jsonify({
                'success': True,
                'data': group_data
            })
            
        except Exception as e:
            logger.error(f"Error getting groups: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    elif request.method == 'POST':
        # Create new group
        try:
            data = request.get_json()
            
            
            # Verify password
            if not verify_password(data.get('password', '')):
                return jsonify({
                    'success': False,
                    'error': 'Invalid password'
                }), 401
            
            # Validate required fields
            if not data.get('name'):
                return jsonify({
                    'success': False,
                    'error': 'Group name is required'
                }), 400
            
            # Check if group name already exists
            existing_group = OutletGroup.query.filter_by(name=data['name']).first()
            if existing_group:
                return jsonify({
                    'success': False,
                    'error': 'Group name already exists'
                }), 400
            
            # Create new group
            group = OutletGroup(
                name=data['name'],
                description=data.get('description', ''),
                outlet_ids=json.dumps(data.get('outlet_ids', [])),
                color=data.get('color', '#667eea')
            )
            
            db.session.add(group)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'data': {
                    'id': group.id,
                    'name': group.name,
                    'description': group.description,
                    'outlet_ids': group.get_outlet_ids(),
                    'color': group.color
                }
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating group: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

@app.route('/api/groups/<int:group_id>', methods=['PUT', 'DELETE'])
def handle_group(group_id):
    """Handle individual group operations"""
    try:
        group = OutletGroup.query.get_or_404(group_id)
        data = request.get_json()
        
        # Verify password
        if not verify_password(data.get('password', '')):
            return jsonify({
                'success': False,
                'error': 'Invalid password'
            }), 401
        
        if request.method == 'PUT':
            # Update group
            if 'name' in data:
                # Check if new name already exists (excluding current group)
                existing_group = OutletGroup.query.filter(
                    OutletGroup.name == data['name'],
                    OutletGroup.id != group_id
                ).first()
                if existing_group:
                    return jsonify({
                        'success': False,
                        'error': 'Group name already exists'
                    }), 400
                group.name = data['name']
            
            if 'description' in data:
                group.description = data['description']
            
            if 'outlet_ids' in data:
                group.set_outlet_ids(data['outlet_ids'])
            
            if 'color' in data:
                group.color = data['color']
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'data': {
                    'id': group.id,
                    'name': group.name,
                    'description': group.description,
                    'outlet_ids': group.get_outlet_ids(),
                    'color': group.color
                }
            })
        
        elif request.method == 'DELETE':
            # Delete group
            db.session.delete(group)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Group deleted successfully'
            })
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error handling group: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/outlets/<int:outlet_id>', methods=['PUT'])
def update_outlet(outlet_id):
    """Update outlet name and description"""
    try:
        outlet = PDUPort.query.get_or_404(outlet_id)
        data = request.get_json()
        
        # Verify password
        if not verify_password(data.get('password', '')):
            return jsonify({
                'success': False,
                'error': 'Invalid password'
            }), 401
        
        # Update outlet
        if 'name' in data:
            outlet.name = data['name']
        if 'description' in data:
            outlet.description = data['description']
        
        outlet.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'id': outlet.id,
                'name': outlet.name,
                'description': outlet.description,
                'port_number': outlet.port_number
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating outlet: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats')
def get_stats():
    """Get system statistics"""
    try:
        # Get total outlets
        total_outlets = PDUPort.query.count()
        active_outlets = PDUPort.query.filter_by(is_active=True).count()
        
        # Get total groups
        total_groups = OutletGroup.query.count()
        
        # Get latest power reading
        latest_reading = PowerReading.query.order_by(PowerReading.timestamp.desc()).first()
        total_power = latest_reading.total_power_watts if latest_reading else 0
        
        # Get total readings count
        total_readings = PowerReading.query.count()
        
        return jsonify({
            'success': True,
            'data': {
                'total_outlets': total_outlets,
                'active_outlets': active_outlets,
                'total_groups': total_groups,
                'total_power_watts': total_power,
                'total_readings': total_readings,
                'last_updated': latest_reading.timestamp.isoformat() if latest_reading else None
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/refresh-outlets')
def refresh_outlets():
    """Manually trigger outlet data refresh"""
    try:
        logger.info("Manual outlet refresh triggered")
        collect_power_data(app)  # Pass the Flask app instance
        
        # Get updated outlet data
        outlets = PDUPort.query.filter_by(is_active=True).all()
        outlet_data = []
        for outlet in outlets:
            latest_reading = PortPowerReading.query.filter_by(
                port_id=outlet.id
            ).order_by(PortPowerReading.timestamp.desc()).first()
            
            power_watts = latest_reading.power_watts if latest_reading else 0
            status = latest_reading.status if latest_reading and latest_reading.status else 'OFF'
            
            outlet_data.append({
                'id': outlet.id,
                'name': outlet.name,
                'port_number': outlet.port_number,
                'description': outlet.description,
                'power_watts': power_watts,
                'status': status,
                'last_updated': latest_reading.timestamp.isoformat() if latest_reading else None
            })
        
        logger.info(f"Manual refresh completed - {len(outlet_data)} outlets")
        return jsonify({
            'success': True,
            'data': outlet_data,
            'message': 'Outlet data refreshed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error refreshing outlets: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/debug-outlets')
def debug_outlets():
    """Debug endpoint to see what's actually in the database"""
    try:
        outlets = PDUPort.query.filter_by(is_active=True).order_by(PDUPort.port_number).all()
        
        debug_data = []
        for outlet in outlets:
            debug_data.append({
                'id': outlet.id,
                'port_number': outlet.port_number,
                'name': outlet.name,
                'description': outlet.description,
                'created_at': outlet.created_at.isoformat() if outlet.created_at else None,
                'updated_at': outlet.updated_at.isoformat() if outlet.updated_at else None
            })
        
        logger.info("=== DATABASE DEBUG INFO ===")
        for outlet in debug_data:
            logger.info(f"Port {outlet['port_number']}: name='{outlet['name']}', updated={outlet['updated_at']}")
        
        return jsonify({
            'success': True,
            'data': debug_data,
            'message': 'Database debug info'
        })
        
    except Exception as e:
        logger.error(f"Error getting debug info: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/test-update/<int:port_number>')
def test_update(port_number):
    """Test updating a port name manually"""
    try:
        port = PDUPort.query.filter_by(port_number=port_number, is_active=True).first()
        if not port:
            return jsonify({
                'success': False,
                'error': f'Port {port_number} not found'
            }), 404
        
        old_name = port.name
        new_name = f"TEST-{port_number}-{datetime.utcnow().strftime('%H%M%S')}"
        
        port.name = new_name
        port.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Verify the update
        updated_port = PDUPort.query.get(port.id)
        
        logger.info(f"TEST UPDATE: Port {port_number} name changed from '{old_name}' to '{updated_port.name}'")
        
        return jsonify({
            'success': True,
            'data': {
                'port_number': port_number,
                'old_name': old_name,
                'new_name': updated_port.name,
                'updated_at': updated_port.updated_at.isoformat()
            },
            'message': 'Test update successful'
        })
        
    except Exception as e:
        logger.error(f"Error testing update: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/update-outlet-names')
def update_outlet_names():
    """Manually trigger SNMP name updates for all outlets"""
    try:
        logger.info("Manual outlet name update triggered")
        
        # Import the collector
        from snmp_collector import RaritanPDUCollector
        
        # Create collector with the main app instance
        collector = RaritanPDUCollector(app)
        
        # Get all ports and update their names
        updated_count = 0
        outlets = PDUPort.query.filter_by(is_active=True).all()
        
        for port in outlets:
            try:
                # Get outlet name from PDU
                outlet_name = collector.get_snmp_value(RARITAN_OIDS['outlet_name'], port.port_number, as_string=True)
                
                if outlet_name and outlet_name != port.name and outlet_name != f'Outlet {port.port_number}':
                    old_name = port.name
                    port.name = outlet_name
                    port.updated_at = datetime.utcnow()
                    db.session.commit()
                    
                    logger.info(f"Updated outlet {port.port_number} name from '{old_name}' to: '{outlet_name}'")
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error updating outlet {port.port_number}: {str(e)}")
        
        logger.info(f"Manual name update completed - {updated_count} outlets updated")
        
        return jsonify({
            'success': True,
            'data': {
                'updated_count': updated_count,
                'total_outlets': len(outlets)
            },
            'message': f'Updated {updated_count} outlet names'
        })
        
    except Exception as e:
        logger.error(f"Error updating outlet names: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/discord/test', methods=['POST'])
def test_discord_webhook():
    """Test Discord webhook connection"""
    try:
        success = send_test_notification(app)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Discord test message sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send Discord test message'
            }), 500
            
    except Exception as e:
        logger.error(f"Error testing Discord webhook: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/discord/monthly-report', methods=['POST'])
def send_monthly_discord_report():
    """Manually trigger monthly Discord report"""
    try:
        success = send_monthly_report(app)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Monthly Discord report sent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send monthly Discord report'
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending monthly Discord report: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def start_data_collection():
    """Start background data collection every minute"""
    def collect_data():
        while True:
            try:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collecting power data...")
                collect_power_data(app)  # Pass the Flask app instance
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Power data collection completed.")
            except Exception as e:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error collecting power data: {str(e)}")
            
            # Wait 60 seconds before next collection
            time.sleep(60)
    
    # Start collection thread
    collection_thread = threading.Thread(target=collect_data, daemon=True)
    collection_thread.start()
    print("Background data collection started (every 60 seconds).")

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
    # Start background data collection
    start_data_collection()
    
    # Run Flask app
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)