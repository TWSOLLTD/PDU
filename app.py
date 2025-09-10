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

from config import DATABASE_URI, FLASK_HOST, FLASK_PORT, FLASK_DEBUG, RARITAN_CONFIG, GROUP_MANAGEMENT_PASSWORD
from models import db, PDU, PDUPort, PowerReading, PortPowerReading, PowerAggregation, SystemSettings, OutletGroup, init_db
from snmp_collector import collect_power_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Secure password hash (Ru5tyt1n#)
ADMIN_PASSWORD_HASH = hashlib.sha256(b'Ru5tyt1n#').hexdigest()

def verify_password(password):
    """Verify password securely"""
    return hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH

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
        now = datetime.utcnow()
        if period == 'day':
            start_time = now - timedelta(hours=24)
            interval_minutes = 60  # Hourly data points
            label_format = '%H:%M'
        elif period == 'week':
            start_time = now - timedelta(days=7)
            interval_minutes = 1440  # Daily data points
            label_format = '%a %d'
        elif period == 'month':
            start_time = now - timedelta(days=30)
            interval_minutes = 1440  # Daily data points
            label_format = '%m/%d'
        elif period == 'year-weekly':
            start_time = now - timedelta(days=365)
            interval_minutes = 10080  # Weekly data points
            label_format = 'Week %W'
        elif period == 'year-monthly':
            start_time = now - timedelta(days=365)
            interval_minutes = 43200  # Monthly data points
            label_format = '%b %Y'
        else:
            start_time = now - timedelta(hours=24)
            interval_minutes = 60
            label_format = '%H:%M'
        
        # Generate time labels
        labels = []
        current_time = start_time
        while current_time <= now:
            labels.append(current_time.strftime(label_format))
            current_time += timedelta(minutes=interval_minutes)
        
        # Get power data for selected outlets
        if outlet_ids:
            outlets_data = []
            for outlet_id in outlet_ids:
                outlet = PDUPort.query.get(outlet_id)
                if outlet:
                    # Get readings for this outlet
                    readings = PortPowerReading.query.filter(
                        PortPowerReading.port_id == outlet_id,
                        PortPowerReading.timestamp >= start_time
                    ).order_by(PortPowerReading.timestamp).all()
                    
                    # Aggregate data by time intervals
                    power_values = []
                    for i, label in enumerate(labels):
                        interval_start = start_time + timedelta(minutes=i * interval_minutes)
                        interval_end = interval_start + timedelta(minutes=interval_minutes)
                        
                        # Find readings in this interval
                        interval_readings = [
                            r for r in readings 
                            if interval_start <= r.timestamp < interval_end
                        ]
                        
                        if interval_readings:
                            # Calculate average power for this interval
                            avg_power = sum(r.power_watts for r in interval_readings) / len(interval_readings)
                            power_values.append(avg_power)
                        else:
                            power_values.append(None)  # Use None instead of 0 for missing data
                    
                    outlets_data.append({
                        'id': outlet.id,
                        'name': outlet.name,
                        'port_number': outlet.port_number,
                        'power_watts': power_values
                    })
            
            return jsonify({
                'success': True,
                'data': {
                    'labels': labels,
                    'outlets': outlets_data
                },
                'period': period,
                'start_time': start_time.isoformat(),
                'end_time': now.isoformat()
            })
        else:
            # No outlets selected
            return jsonify({
                'success': True,
                'data': {
                    'labels': labels,
                    'outlets': []
                },
                'period': period,
                'start_time': start_time.isoformat(),
                'end_time': now.isoformat()
            })
        
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
            
            # Determine status based on power consumption
            power_watts = latest_reading.power_watts if latest_reading else 0
            status = 'ON' if power_watts > 5 else 'OFF'  # Consider >5W as ON
            
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
            status = 'ON' if power_watts > 5 else 'OFF'
            
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