import os
from dotenv import load_dotenv

load_dotenv()

# PDU Configuration
PDUS = {
    'PDU1': {
        'name': 'Right PDU',
        'ip': '172.0.250.10',
        'username': 'admin',
        'auth_passphrase': 'testingtesting123',
        'privacy_passphrase': 'testingtesting123',
        'auth_protocol': 'SHA',
        'privacy_protocol': 'AES'
    },
    'PDU2': {
        'name': 'Left PDU',
        'ip': '172.0.250.11',
        'username': 'admin',
        'auth_passphrase': 'testingtesting123',
        'privacy_passphrase': 'testingtesting123',
        'auth_protocol': 'SHA',
        'privacy_protocol': 'AES'
    }
}

# SNMP Configuration
SNMP_PORT = 161
SNMP_TIMEOUT = 3
SNMP_RETRIES = 3

# Data Collection Settings
COLLECTION_INTERVAL = 60  # seconds
POWER_OID = '1.3.6.1.4.1.318.1.1.12.3.3.1.1.2.1'  # APC PDU power OID

# Database Configuration
DATABASE_URI = 'sqlite:///pdu_monitor.db'

# Web Interface Configuration
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5000
FLASK_DEBUG = True

# Webhook Configuration
WEBHOOK_SECRET = 'your-secret-key-here'  # Change this to a secure random string
WEBHOOK_PORT = 5001

