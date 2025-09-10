import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Raritan PDU Configuration
RARITAN_CONFIG = {
    'name': 'Raritan PX3-5892',
    'ip': os.getenv('PDU_IP', '172.0.250.9'),  # Default fallback
    'username': 'admin',    # Update with your credentials
    'password': 'admin',    # Update with your credentials
    'snmp_community': 'public',  # SNMP community string (not used for v3)
    'snmp_port': 161,
    'snmp_timeout': 10,
    'snmp_retries': 5,
    # SNMP v3 Configuration - Now using environment variables
    'snmp_username': os.getenv('SNMP_USERNAME'),
    'snmp_auth_protocol': 'SHA-256',
    'snmp_priv_protocol': 'AES-128',
    'snmp_auth_password': os.getenv('SNMP_AUTH_PASSWORD'),
    'snmp_priv_password': os.getenv('SNMP_PRIV_PASSWORD')
}

# SNMP Configuration for Raritan PX3-5892
SNMP_PORT = 161
SNMP_TIMEOUT = 10
SNMP_RETRIES = 5

# SNMP v3 Configuration - Using environment variables
SNMP_USERNAME = os.getenv('SNMP_USERNAME')
SNMP_AUTH_PROTOCOL = 'SHA-256'
SNMP_PRIV_PROTOCOL = 'AES-128'
SNMP_AUTH_PASSWORD = os.getenv('SNMP_AUTH_PASSWORD')
SNMP_PRIV_PASSWORD = os.getenv('SNMP_PRIV_PASSWORD')

# Raritan PX3-5892 SNMP OIDs - EXACT COPY from raritan_snmp_commands.txt
# These are the EXACT OIDs that were tested and verified working
RARITAN_OIDS = {
    # Total PDU power (Watts) - Line 9 from your commands
    'total_power_watts': '1.3.6.1.4.1.13742.6.5.2.3.1.4.1.1.5',
    
    # Outlet power (Watts) - Lines 15-50 from your commands (WITH leading dot)
    'outlet_power_watts': '.1.3.6.1.4.1.13742.6.5.4.3.1.4.1.{outlet}.5',
    
    # Outlet status (7=ON, 8=OFF) - Lines 57-92 from your commands (WITH leading dot)
    'outlet_status': '.1.3.6.1.4.1.13742.6.5.4.3.1.3.1.{outlet}.14',
    
    # Outlet names - Lines 99-134 from your commands (NO leading dot)
    'outlet_name': '1.3.6.1.4.1.13742.6.3.5.3.1.3.1.{outlet}',
    
    # Port OIDs (same as outlet OIDs)
    'port_power_watts': '.1.3.6.1.4.1.13742.6.5.4.3.1.4.1.{port}.5',
    'port_status': '.1.3.6.1.4.1.13742.6.5.4.3.1.3.1.{port}.14',
    'port_name': '1.3.6.1.4.1.13742.6.3.5.3.1.3.1.{port}',
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
GROUP_MANAGEMENT_PASSWORD = os.getenv('GROUP_MANAGEMENT_PASSWORD')  # Secure password for group management

# Discord Webhook Configuration
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')  # Discord webhook URL for alerts

