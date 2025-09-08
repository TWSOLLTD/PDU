import os
from dotenv import load_dotenv

load_dotenv()

# Raritan PDU Configuration
RARITAN_CONFIG = {
    'name': 'Raritan PX3-5892',
    'ip': '172.0.250.9',  # New PDU IP address
    'username': 'admin',    # Update with your credentials
    'password': 'admin',    # Update with your credentials
    'snmp_community': 'public',  # SNMP community string
    'snmp_port': 161,
    'snmp_timeout': 10,
    'snmp_retries': 5
}

# SNMP Configuration for Raritan PX3-5892
SNMP_PORT = 161
SNMP_TIMEOUT = 10
SNMP_RETRIES = 5

# Raritan PX3-5892 SNMP OIDs
RARITAN_OIDS = {
    # Total PDU power
    'total_power_watts': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.1.1',  # Total power in watts
    'total_power_va': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.1.2',     # Total apparent power
    'total_current': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.1.3',      # Total current
    
    # Per-outlet power (replace {outlet} with outlet number 1-36)
    # Based on SNMP walk: 1.3.6.1.4.1.13742.6.3.3.4.1.7.1.1.{outlet} = power watts
    'outlet_power_watts': '1.3.6.1.4.1.13742.6.3.3.4.1.7.1.1.{outlet}',  # Outlet power in watts
    'outlet_current': '1.3.6.1.4.1.13742.6.3.3.4.1.8.1.1.{outlet}',      # Outlet current
    'outlet_status': '1.3.6.1.4.1.13742.6.3.3.4.1.9.1.1.{outlet}',       # Outlet status (on/off)
    'outlet_name': '1.3.6.1.4.1.13742.6.3.3.3.1.2.1.{outlet}',          # Outlet name/label
    
    # Legacy port OIDs (for backward compatibility)
    'port_power_watts': '1.3.6.1.4.1.13742.6.3.3.4.1.7.1.1.{port}',  # Port power in watts
    'port_current': '1.3.6.1.4.1.13742.6.3.3.4.1.8.1.1.{port}',      # Port current
    'port_status': '1.3.6.1.4.1.13742.6.3.3.4.1.9.1.1.{port}',       # Port status (on/off)
    'port_name': '1.3.6.1.4.1.13742.6.3.3.3.1.2.1.{port}',          # Port name/label
}

# Data Collection Settings
COLLECTION_INTERVAL = 60  # seconds - collect data every minute
POWER_OID = RARITAN_OIDS['total_power_watts']  # Default to total power OID

# Alert Configuration
ALERT_CONFIG = {
    'high_power_threshold_watts': 800,  # Alert if power exceeds this for sustained period
    'high_power_duration_minutes': 5,  # How long power must be high before alerting
    'zero_power_sustained_readings': 2,  # How many consecutive zero readings before alerting
    'power_spike_threshold_percent': 50,  # Alert if power increases by this percentage
    'power_spike_sustained_threshold': 30,  # Minimum sustained increase percentage
    'low_efficiency_threshold': 0.8,  # Power factor threshold for efficiency alerts
    'offline_timeout_minutes': 5,  # How long before PDU is considered offline
}

# Database Configuration
DATABASE_URI = 'sqlite:///pdu_monitor.db'

# Web Interface Configuration
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = True

# Webhook Configuration
WEBHOOK_SECRET = '83f94680ae1190173ed57c776bbfd1ad55da3dde6951e406f09003fabd7e93a2'
WEBHOOK_PORT = 5001

# Group Management Configuration
GROUP_MANAGEMENT_PASSWORD = 'admin123'  # Change this to a secure password

