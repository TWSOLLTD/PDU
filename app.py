#!/usr/bin/env python3
"""
Raritan PDU Power Monitoring Web Application
Flask-based web interface for monitoring Raritan PDU PX3-5892 power consumption
"""

from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import calendar
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
cache_lock = threading.RLock()

# Cache TTL (seconds) per period
PERIOD_CACHE_TTLS = {
    'day-10min': 60,            # refresh every minute
    'week-10min': 60,           # refresh every minute
    'day': 3600,                # refresh every hour
    'week': 86400,              # refresh every day
    'month': 86400,             # refresh every day
    'year-weekly': 86400,       # refresh every day
    'year-monthly': 86400       # refresh every day
}

DEFAULT_CACHE_TIMEZONE = os.getenv('DEFAULT_CACHE_TIMEZONE', 'Europe/London')
CACHE_WARM_PERIODS = tuple(PERIOD_CACHE_TTLS.keys())
CACHE_WARM_INCLUDE_ALL_OUTLETS = os.getenv('CACHE_WARM_INCLUDE_ALL_OUTLETS', 'true').lower() == 'true'
ENABLE_CACHE_WARMUP = os.getenv('ENABLE_CACHE_WARMUP', 'true').lower() == 'true'
PERIOD_REFRESH_INTERVALS = {
    period: int(os.getenv(f'CACHE_REFRESH_INTERVAL_{period.upper().replace("-", "_")}', ttl))
    for period, ttl in PERIOD_CACHE_TTLS.items()
}
_cache_warm_thread_started = False

# Cache status tracking for precomputed datasets
CACHE_STATUS_READY = 'ready'
CACHE_STATUS_PREPARING = 'preparing'
CACHE_STATUS_FAILED = 'failed'


def get_cache_ttl(period: str) -> int:
    """Return cache TTL in seconds for the given period."""
    return PERIOD_CACHE_TTLS.get(period, 0)


def make_cache_key(period: str, outlet_ids: list, user_timezone: str) -> tuple:
    """Construct cache key based on request parameters."""
    sorted_ids = tuple(sorted(outlet_ids))
    return (period, sorted_ids, user_timezone)


def get_cached_payload(cache_key, cache_ttl):
    """Return cached payload if present and fresh."""
    with cache_lock:
        cached_entry = power_data_cache.get(cache_key)
    if cached_entry and (time.time() - cached_entry['timestamp']) < cache_ttl:
        return cached_entry['payload']
    return None


def set_cache_entry(cache_key, payload):
    """Store payload in cache."""
    with cache_lock:
        power_data_cache[cache_key] = {
            'timestamp': time.time(),
            'payload': payload
        }


def calculate_power_data(period: str, outlet_ids: list, user_timezone: str) -> dict:
    """Calculate power chart payload for the given period and outlets."""
    utc_now = datetime.utcnow()
    user_tz = ZoneInfo(user_timezone)
    now = utc_now.replace(tzinfo=timezone.utc).astimezone(user_tz)

    # Normalize outlet IDs to integers
    outlet_ids = [int(outlet_id) for outlet_id in outlet_ids]

    if period == 'day':
        labels = [f"{i:02d}:00" for i in range(24)]
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        interval_minutes = 60
    elif period == 'day-10min':
        labels = [f"{hour:02d}:{minute:02d}"
                  for hour in range(24)
                  for minute in range(0, 60, 10)]
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        interval_minutes = 10
    elif period == 'week-10min':
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        labels = [
            f"{days[day_idx]} {hour:02d}:{minute:02d}"
            for day_idx in range(7)
            for hour in range(24)
            for minute in range(0, 60, 10)
        ]
        days_since_monday = now.weekday()
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        interval_minutes = 10
    elif period == 'week':
        labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        days_since_monday = now.weekday()
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        interval_minutes = 1440
    elif period == 'month':
        last_day = calendar.monthrange(now.year, now.month)[1]
        labels = [f"{day:02d}" for day in range(1, last_day + 1)]
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        interval_minutes = 1440
    elif period == 'year-weekly':
        labels = []
        current_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        while current_date.weekday() != 0:
            current_date += timedelta(days=1)
        for week in range(52):
            week_start = current_date + timedelta(weeks=week)
            week_end = week_start + timedelta(days=6)
            month_name = week_start.strftime('%b')
            labels.append(f"{month_name} {week_start.day}-{week_end.day}")
        start_time = current_date
        interval_minutes = 10080
    elif period == 'year-monthly':
        labels = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        interval_minutes = 43200
    else:
        labels = [f"{i:02d}:00" for i in range(24)]
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        interval_minutes = 60

    start_time_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)

    if outlet_ids:
        outlets_data = []
        for outlet_id in outlet_ids:
            outlet = PDUPort.query.get(outlet_id)
            if not outlet:
                continue

            readings = PortPowerReading.query.filter(
                PortPowerReading.port_id == outlet_id,
                PortPowerReading.timestamp >= start_time_utc
            ).order_by(PortPowerReading.timestamp).all()

            power_values = []
            energy_values = []
            for index in range(len(labels)):
                interval_start = start_time + timedelta(minutes=index * interval_minutes)
                interval_end = interval_start + timedelta(minutes=interval_minutes)

                interval_start_utc = interval_start.astimezone(timezone.utc).replace(tzinfo=None)
                interval_end_utc = interval_end.astimezone(timezone.utc).replace(tzinfo=None)

                interval_readings = [
                    reading for reading in readings
                    if interval_start_utc <= reading.timestamp < interval_end_utc
                ]

                if interval_readings:
                    avg_power = sum(r.power_watts for r in interval_readings) / len(interval_readings)
                    power_values.append(round(avg_power, 1))

                    total_energy_kwh = 0
                    for reading_index in range(len(interval_readings) - 1):
                        time_diff = (interval_readings[reading_index + 1].timestamp - interval_readings[reading_index].timestamp).total_seconds() / 3600
                        energy_kwh = (interval_readings[reading_index].power_watts * time_diff) / 1000
                        total_energy_kwh += energy_kwh

                    if interval_readings:
                        last_energy = (interval_readings[-1].power_watts * (1 / 60)) / 1000
                        total_energy_kwh += last_energy

                    energy_values.append(round(total_energy_kwh, 3))
                else:
                    power_values.append(0)
                    energy_values.append(0)

            outlets_data.append({
                'id': outlet.id,
                'name': outlet.name,
                'port_number': outlet.port_number,
                'power_watts': power_values,
                'energy_kwh': energy_values
            })

        return {
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

    # No outlets selected
    return {
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


def warm_power_data_cache_for_timezone(user_timezone: str | None = None, periods: list | None = None):
    """Pre-compute cache entries for all groups and specified periods."""
    tz = user_timezone or DEFAULT_CACHE_TIMEZONE
    periods_to_warm = periods or CACHE_WARM_PERIODS

    logger.info(f"Pre-warming power data cache for timezone '{tz}' periods={list(periods_to_warm)}")

    try:
        groups = OutletGroup.query.all()
        active_outlets = PDUPort.query.filter_by(is_active=True).all()
    except Exception as exc:
        logger.error(f"Unable to warm cache (database error): {exc}")
        return

    outlet_combinations = []

    if CACHE_WARM_INCLUDE_ALL_OUTLETS and active_outlets:
        all_ids = tuple(sorted(port.id for port in active_outlets))
        outlet_combinations.append((all_ids, 'all_active_outlets'))

    for group in groups:
        group_outlet_ids = tuple(sorted(group.get_outlet_ids() or []))
        if group_outlet_ids:
            outlet_combinations.append((group_outlet_ids, f"group_{group.id}"))

    seen = set()
    for outlet_ids_tuple, label in outlet_combinations:
        if not outlet_ids_tuple or outlet_ids_tuple in seen:
            continue
        seen.add(outlet_ids_tuple)
        outlet_id_list = list(outlet_ids_tuple)

        for period in periods_to_warm:
            ttl = PERIOD_CACHE_TTLS.get(period, 0)
            if ttl <= 0:
                continue

            cache_key = make_cache_key(period, outlet_id_list, tz)
            if get_cached_payload(cache_key, ttl):
                continue

            try:
                payload = calculate_power_data(period, outlet_id_list, tz)
                set_cache_entry(cache_key, payload)
                logger.info(f"Cache warmed for {label} period='{period}' timezone='{tz}'")
            except Exception as exc:
                logger.error(f"Failed to warm cache for {label} period='{period}' timezone='{tz}': {exc}")

    logger.info("Power data cache pre-warm completed for requested periods")


def start_cache_warmup_thread():
    """Start background thread to keep cache pre-populated."""
    global _cache_warm_thread_started

    if not ENABLE_CACHE_WARMUP or _cache_warm_thread_started:
        return

    def cache_warmup_loop():
        with app.app_context():
            next_refresh = {period: 0 for period in PERIOD_REFRESH_INTERVALS}

            while True:
                now = time.time()
                due_periods = [period for period, run_at in next_refresh.items() if now >= run_at]

                if due_periods:
                    for period in due_periods:
                        try:
                            warm_power_data_cache_for_timezone(DEFAULT_CACHE_TIMEZONE, periods=[period])
                        except Exception as exc:
                            logger.error(f"Background cache warmup failed for period '{period}': {exc}")
                        finally:
                            next_interval = PERIOD_REFRESH_INTERVALS.get(period, 300)
                            next_refresh[period] = time.time() + next_interval
                else:
                    # Nothing due yet; sleep until the next refresh is scheduled
                    sleep_for = min(
                        max(run_at - now, 1)
                        for run_at in next_refresh.values()
                    )
                    time.sleep(sleep_for)
                    continue

                # After processing due periods, sleep briefly before checking again
                time.sleep(1)

    warm_thread = threading.Thread(target=cache_warmup_loop, name="PowerDataCacheWarmup", daemon=True)
    warm_thread.start()
    _cache_warm_thread_started = True


start_cache_warmup_thread()


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
        
        user_timezone = request.headers.get('X-User-Timezone', 'Europe/London')
        cache_ttl = get_cache_ttl(period)
        cache_key = make_cache_key(period, outlet_ids, user_timezone) if cache_ttl > 0 else None

        if cache_key:
            cached_payload = get_cached_payload(cache_key, cache_ttl)
            if cached_payload:
                logger.info(f"Serving cached power data for key={cache_key}")
                return jsonify(cached_payload)

        response_payload = calculate_power_data(period, outlet_ids, user_timezone)

        if cache_key:
            set_cache_entry(cache_key, response_payload)

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