import os
from dotenv import load_dotenv

load_dotenv()

# Raritan PDU Configuration
RARITAN_CONFIG = {
    'name': 'Raritan PX3-5892',
    'ip': '172.0.250.9',  # New PDU IP address
    'username': 'admin',    # Update with your credentials
    'password': 'admin',    # Update with your credentials
    'snmp_community': 'public',  # SNMP community string (not used for v3)
    'snmp_port': 161,
    'snmp_timeout': 10,
    'snmp_retries': 5,
    # SNMP v3 Configuration
    'snmp_username': 'snmpuser',
    'snmp_auth_protocol': 'SHA-256',
    'snmp_priv_protocol': 'AES-128',
    'snmp_auth_password': '91W1CGVNkhTXA<^W',
    'snmp_priv_password': '91W1CGVNkhTXA<^W'
}

# SNMP Configuration for Raritan PX3-5892
SNMP_PORT = 161
SNMP_TIMEOUT = 10
SNMP_RETRIES = 5

# SNMP v3 Configuration
SNMP_USERNAME = 'snmpuser'
SNMP_AUTH_PROTOCOL = 'SHA-256'
SNMP_PRIV_PROTOCOL = 'AES-128'
SNMP_AUTH_PASSWORD = '91W1CGVNkhTXA<^W'
SNMP_PRIV_PASSWORD = '91W1CGVNkhTXA<^W'

# Raritan PX3-5892 SNMP OIDs (using SNMP v3 with correct OIDs for all 36 outlets)
RARITAN_OIDS = {
    # Total PDU power (using inlet measurements)
    'total_power_watts': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.1.1',  # Total power
    'total_current': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.1.3',      # Total current
    
    # Per-outlet measurements (CORRECTED OIDs from actual SNMP walk data)
    # Structure: 1.3.6.1.4.1.13742.6.3.5.4.1.{tableId}.1.{outletId}.{sensorType}
    # tableId: 11=measurements, 21-24=different measurement tables, outletId=1-36, sensorType: 4=activePower, 0=rmsCurrent, 13=onOff
    'outlet_power_watts': '1.3.6.1.4.1.13742.6.3.5.4.1.11.1.{outlet}.4',  # Outlet power (activePower) - main measurements table
    'outlet_current': '1.3.6.1.4.1.13742.6.3.5.4.1.11.1.{outlet}.0',      # Outlet current (rmsCurrent) - main measurements table
    'outlet_status': '1.3.6.1.4.1.13742.6.3.5.4.1.11.1.{outlet}.13',      # Outlet status (onOff) - main measurements table
    
    # Outlet configuration (names - all 36 outlets accessible)
    'outlet_name': '1.3.6.1.4.1.13742.6.3.5.3.1.3.1.{outlet}',           # Outlet name (all 36)
    'outlet_label': '1.3.6.1.4.1.13742.6.3.5.3.1.2.1.{outlet}',          # Outlet label (all 36)
    
    # Port OIDs (same as outlet OIDs with correct structure from SNMP walk)
    'port_power_watts': '1.3.6.1.4.1.13742.6.3.5.4.1.11.1.{port}.4',  # Port power in watts (activePower) - main measurements table
    'port_current': '1.3.6.1.4.1.13742.6.3.5.4.1.11.1.{port}.0',      # Port current (rmsCurrent) - main measurements table
    'port_status': '1.3.6.1.4.1.13742.6.3.5.4.1.11.1.{port}.13',      # Port status (onOff) - main measurements table
    'port_name': '1.3.6.1.4.1.13742.6.3.5.3.1.3.1.{port}',          # Port name
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
GROUP_MANAGEMENT_PASSWORD = 'Ru5tyt1n#'  # Secure password for group management

