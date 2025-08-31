# PDU Power Monitoring System

A comprehensive system for monitoring APC PDU power consumption via SNMP with a modern web dashboard.

**Repository:** [https://github.com/TWSOLLTD/PDU](https://github.com/TWSOLLTD/PDU)

## Features

- **Real-time Monitoring**: Collects power consumption data from APC PDUs via SNMPv3
- **Multi-PDU Support**: Monitor multiple PDUs simultaneously
- **Time-based Views**: View data by day (hourly), week (daily), month (daily), and year (monthly)
- **Interactive Charts**: Beautiful charts powered by Plotly.js showing power trends
- **Statistics Dashboard**: Comprehensive statistics including total kWh, average power, peak power, etc.
- **Responsive Design**: Modern, mobile-friendly web interface
- **Automatic Data Collection**: Scheduled data collection with configurable intervals
- **Data Aggregation**: Efficient storage and retrieval of time-based power consumption data

## System Requirements

- Python 3.8+
- Debian/Ubuntu Linux (or similar)
- Network access to PDU devices
- SNMPv3 support on PDUs
- Systemd (for service management)

## Quick Setup Summary

For `/opt/PDU-NEW/` installation:

```bash
# 1. Create directory
mkdir -p /opt/PDU-NEW
cd /opt/PDU-NEW

# 2. Install dependencies
apt update
apt install -y git python3 python3-pip python3-venv snmp snmp-mibs-downloader build-essential python3-dev libssl-dev

# 3. Clone the repository
git clone https://github.com/TWSOLLTD/PDU .

# 4. Set up Python environment
python3 -m venv pdu_env
source pdu_env/bin/activate
pip install -r requirements.txt

# 5. Initialize database
python3 -c "from app import create_app; app = create_app()"

# 6. Test SNMP connection
python3 snmp_collector.py

# 7. Start the system
chmod +x start.sh
./start.sh
```

## Installation

### 1. Set Up Project Directory

```bash
# Create the project directory
mkdir -p /opt/PDU-NEW
cd /opt/PDU-NEW
```

### 2. Install System Dependencies

```bash
# Update package list
apt update

# Install Git and Python 3
apt install -y git python3 python3-pip python3-venv

# Install system dependencies for SNMP and development
apt install -y snmp snmp-mibs-downloader build-essential python3-dev libssl-dev
```

### 3. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/TWSOLLTD/PDU .
```

### 4. Install Python Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv pdu_env
source pdu_env/bin/activate

# Install Python packages
pip install -r requirements.txt

# Note: Keep the virtual environment activated for the next steps
```

### 5. Configure PDU Settings

Edit `config.py` to match your PDU configuration:

```python
PDUS = {
    'PDU1': {
        'name': 'Right PDU',
        'ip': '172.0.250.10',  # Your PDU IP
        'username': 'admin',
        'auth_passphrase': 'your_auth_passphrase',
        'privacy_passphrase': 'your_privacy_passphrase',
        'auth_protocol': 'SHA',
        'privacy_protocol': 'AES'
    },
    'PDU2': {
        'name': 'Left PDU',
        'ip': '172.0.250.11',  # Your second PDU IP
        'username': 'admin',
        'auth_passphrase': 'your_auth_passphrase',
        'privacy_passphrase': 'your_privacy_passphrase',
        'auth_protocol': 'SHA',
        'privacy_protocol': 'AES'
    }
}
```

### 6. Initialize Database

```bash
python3 -c "from app import create_app; app = create_app()"
```

## Usage

### Starting the Web Dashboard

```bash
python3 app.py
```

The web interface will be available at `http://localhost:5000`

### Starting the Data Collector

```bash
python3 scheduler.py
```

This will start collecting data from your PDUs every minute (configurable in `config.py`).

### Manual Data Collection

To collect data manually:

```bash
python3 snmp_collector.py
```

### Using the Startup Script

The easiest way to run the system is using the provided startup script:

```bash
# Make the script executable (first time only)
chmod +x start.sh

# Start the system
./start.sh
```

This will start both the data collector and web dashboard automatically.

### Running as a System Service (Recommended for Production)

For production use, you can create a systemd service:

1. **Create the service file:**

```bash
nano /etc/systemd/system/pdu-monitor.service
```

2. **Add the following content:**

```ini
[Unit]
Description=PDU Power Monitoring System
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/opt/PDU-NEW
Environment=PATH=/opt/PDU-NEW/pdu_env/bin
ExecStart=/opt/PDU-NEW/pdu_env/bin/python3 /opt/PDU-NEW/scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Note:** Replace `your_username` with your actual username.

3. **Enable and start the service:**

```bash
systemctl daemon-reload
systemctl enable pdu-monitor
systemctl start pdu-monitor
systemctl status pdu-monitor
```

4. **View logs:**

```bash
journalctl -u pdu-monitor -f
```

### Running the Web Dashboard

The web dashboard needs to be run separately. You can either:

**Option A: Run manually when needed**
```bash
cd /opt/PDU-NEW
source pdu_env/bin/activate
python3 app.py
```

**Option B: Create a separate systemd service for the web dashboard**
```bash
nano /etc/systemd/system/pdu-web.service
```

Add this content:
```ini
[Unit]
Description=PDU Web Dashboard
After=network.target pdu-monitor.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/opt/PDU-NEW
Environment=PATH=/opt/PDU-NEW/pdu_env/bin
ExecStart=/opt/PDU-NEW/pdu_env/bin/python3 /opt/PDU-NEW/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start it:
```bash
systemctl daemon-reload
systemctl enable pdu-web
systemctl start pdu-web
```

## Configuration Options

### Data Collection Interval

Edit `config.py` to change how often data is collected:

```python
COLLECTION_INTERVAL = 60  # seconds
```

### SNMP Settings

```python
SNMP_PORT = 161
SNMP_TIMEOUT = 3
SNMP_RETRIES = 3
```

### Web Interface Settings

```python
FLASK_HOST = '0.0.0.0'  # Listen on all interfaces
FLASK_PORT = 5000
FLASK_DEBUG = True
```

## Web Dashboard Features

### PDU Status Overview
- Real-time status of each PDU
- Current power consumption in watts and kilowatts
- Online/offline status indicators
- IP address information

### Time Period Selection
- **Day View**: Hourly breakdown of power consumption
- **Week View**: Daily totals for the last 7 days
- **Month View**: Daily totals for the last 30 days
- **Year View**: Monthly totals for the last 12 months

### PDU Selection
- Checkbox controls to select which PDUs to display
- Individual PDU data or combined totals
- Real-time filtering of charts and statistics

### Power Consumption Charts
- Interactive line charts showing power trends
- Dual Y-axis: kWh consumption and power in watts
- Hover tooltips with detailed information
- Responsive design for all screen sizes

### Statistics Dashboard
- Total kWh consumption for selected period
- Average, maximum, and minimum power consumption
- Peak consumption time identification
- Real-time updates every 30 seconds

## API Endpoints

### GET `/api/power-data`
Get power consumption data for charts.

**Parameters:**
- `period`: Time period (day, week, month, year)
- `pdu_ids[]`: Array of PDU IDs to include

**Response:**
```json
{
  "success": true,
  "data": {
    "labels": ["00:00", "01:00", ...],
    "kwh": [1.2, 1.5, ...],
    "avg_power": [1200.0, 1500.0, ...],
    "max_power": [1300.0, 1600.0, ...],
    "min_power": [1100.0, 1400.0, ...]
  }
}
```

### GET `/api/current-status`
Get current status of all PDUs.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "PDU-1",
      "ip": "172.0.250.10",
      "current_power_watts": 1250.5,
      "current_power_kw": 1.2505,
      "last_reading": "2024-01-01T12:00:00",
      "status": "online"
    }
  ]
}
```

### GET `/api/statistics`
Get power consumption statistics.

**Parameters:**
- `period`: Time period (day, week, month, year)
- `pdu_ids[]`: Array of PDU IDs to include

**Response:**
```json
{
  "success": true,
  "data": {
    "total_kwh": 28.5,
    "avg_power_watts": 1187.5,
    "max_power_watts": 1500.0,
    "min_power_watts": 950.0,
    "peak_hour": "2024-01-01 14:00"
  }
}
```

### GET `/api/pdus`
Get list of all configured PDUs.

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "PDU-1",
      "ip": "172.0.250.10"
    }
  ]
}
```

## Database Schema

### Tables

#### `pdus`
- `id`: Primary key
- `name`: PDU name
- `ip_address`: PDU IP address
- `created_at`: Record creation timestamp

#### `power_readings`
- `id`: Primary key
- `pdu_id`: Foreign key to pdus table
- `timestamp`: Reading timestamp
- `power_watts`: Power consumption in watts
- `power_kw`: Power consumption in kilowatts

#### `power_aggregations`
- `id`: Primary key
- `pdu_id`: Foreign key to pdus table (NULL for combined)
- `period_type`: Aggregation type (hourly, daily, monthly)
- `period_start`: Period start timestamp
- `period_end`: Period end timestamp
- `total_kwh`: Total kWh for period
- `avg_power_watts`: Average power in watts
- `max_power_watts`: Maximum power in watts
- `min_power_watts`: Minimum power in watts

## Troubleshooting

### Common Issues

1. **SNMP Connection Failed**
   - Verify PDU IP addresses are correct
   - Check SNMP credentials and protocols
   - Ensure network connectivity
   - Verify SNMP port (default: 161)

2. **No Data in Charts**
   - Check if data collector is running
   - Verify database has power readings
   - Check browser console for JavaScript errors

3. **Database Errors**
   - Ensure SQLite database is writable
   - Check database initialization
   - Verify table structure

### Logs

The system generates several log files:
- `pdu_collector.log`: SNMP collection logs
- `pdu_scheduler.log`: Scheduler operation logs
- Flask application logs (console output)

## Security Considerations

- SNMPv3 authentication and privacy are enabled by default
- Web interface is accessible on all network interfaces (configurable)
- No authentication on web interface (add if needed for production)
- Database is stored locally (consider encryption for sensitive environments)

## Performance

- Data collection: Every 60 seconds (configurable)
- Web dashboard refresh: Every 30 seconds
- Chart data is aggregated for efficient storage
- SQLite database with proper indexing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs
3. Open an issue on GitHub
4. Contact the development team

## Future Enhancements

- Email alerts for power consumption thresholds
- Export functionality (CSV, PDF reports)
- User authentication and role-based access
- REST API for external integrations
- Historical data archiving
- Power cost calculations
- Environmental impact metrics
