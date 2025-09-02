import os
from dotenv import load_dotenv

load_dotenv()

# Raritan PDU Configuration
RARITAN_CONFIG = {
    'name': 'Raritan PX3-5892',
    'ip': '192.168.1.100',  # Update this to your PDU's actual IP
    'username': 'admin',    # Update with your credentials
    'password': 'admin',    # Update with your credentials
    'snmp_community': 'public',  # Update if different
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
    
    # Per-port power (replace {port} with port number 1-36)
    'port_power_watts': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.1',  # Port power in watts
    'port_power_va': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.2',     # Port apparent power
    'port_current': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.3',      # Port current
    'port_voltage': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.4',      # Port voltage
    'port_power_factor': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.5', # Port power factor
    
    # Port status and names
    'port_status': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.6',       # Port status (on/off)
    'port_name': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.7',         # Port name/label
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

