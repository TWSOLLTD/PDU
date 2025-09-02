# Raritan PDU Power Monitoring System

A modern, real-time power monitoring system designed specifically for the **Raritan PDU PX3-5892** with per-port monitoring capabilities.

## 🚀 Features

### Core Monitoring
- **Per-Port Power Monitoring**: Individual power consumption tracking for all 36 ports
- **Real-Time Data**: Live power readings updated every minute
- **Total PDU Power**: Aggregate power consumption across all ports
- **Port Status Tracking**: Online/offline status for each port
- **Port Naming**: Customizable port names that sync with PDU configuration

### Advanced Analytics
- **Multi-Period Views**: Day, Week, Month, and Year data visualization
- **Per-Port Graphs**: Individual line graphs for each port with unique colors
- **Total Power Graphs**: Aggregate power consumption trends
- **Energy Consumption**: kWh tracking and visualization
- **15-Minute Intervals**: High-resolution data collection for detailed analysis

### Modern UI
- **Dark Mode Design**: Beautiful, modern interface with dark theme
- **Responsive Layout**: Works perfectly on desktop, tablet, and mobile
- **Interactive Charts**: Plotly.js powered charts with hover details
- **Real-Time Updates**: Auto-refresh every 30 seconds
- **Export Capabilities**: CSV data export for analysis

### Technical Features
- **SNMP Integration**: Direct SNMP communication with Raritan PDU
- **Database Storage**: SQLite database for reliable data persistence
- **RESTful API**: Clean API endpoints for data access
- **Error Handling**: Robust error handling and logging
- **Port Name Sync**: Automatic synchronization of port names from PDU

## 📋 Requirements

- Python 3.8+
- Network access to Raritan PDU PX3-5892
- SNMP enabled on PDU (v2c recommended)
- Web browser with JavaScript enabled

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd PDU
```

### 2. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 3. Configure PDU Settings
Edit `config.py` and update the Raritan PDU configuration:

```python
RARITAN_CONFIG = {
    'name': 'Raritan PX3-5892',
    'ip': '192.168.1.100',  # Your PDU's IP address
    'username': 'admin',     # PDU username
    'password': 'admin',     # PDU password
    'snmp_community': 'public',  # SNMP community string
    'snmp_port': 161,
    'snmp_timeout': 10,
    'snmp_retries': 5
}
```

### 4. Initialize Database
```bash
python3 -c "from app import create_app; app = create_app()"
```

## 🚀 Quick Start

### Start the System
```bash
chmod +x start.sh
./start.sh
```

### Access the Dashboard
Open your web browser and navigate to:
```
http://localhost:5000
```

### Stop the System
```bash
chmod +x stop.sh
./stop.sh
```

## 📊 Dashboard Features

### Main Dashboard
- **Statistics Cards**: Total power, energy consumption, peak power, and online ports
- **Port Grid**: Individual cards showing each port's power consumption and status
- **Real-Time Updates**: Auto-refresh every 30 seconds

### Power Consumption Charts
- **Total Power View**: Aggregate power consumption across all ports
- **Per-Port View**: Individual line graphs for each port
- **Time Periods**: Day (15-min intervals), Week, Month, Year
- **Interactive**: Hover for detailed information

### Energy Consumption Charts
- **Bar Charts**: Energy consumption in kWh
- **Multiple Periods**: Day, Week, Month, Year views
- **Total Energy**: Cumulative energy usage tracking

### Port Management
- **Click to Rename**: Click any port name to edit it
- **Status Indicators**: Visual online/offline status
- **Detailed Metrics**: Power, current, voltage, and power factor

## 🔧 Configuration

### SNMP OIDs
The system uses the following SNMP OIDs for Raritan PX3-5892:

```python
RARITAN_OIDS = {
    'total_power_watts': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.1.1',
    'port_power_watts': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.1',
    'port_current': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.3',
    'port_voltage': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.4',
    'port_power_factor': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.5',
    'port_name': '1.3.6.1.4.1.13742.6.3.2.4.1.2.1.{port}.7',
}
```

### Data Collection
- **Interval**: 60 seconds (configurable in `config.py`)
- **Storage**: SQLite database (`pdu_monitor.db`)
- **Logging**: Detailed logs in `logs/` directory

## 📁 File Structure

 ```
 PDU/
 ├── app.py                 # Main Flask application
 ├── snmp_collector.py     # SNMP data collector
 ├── models.py             # Database models
 ├── config.py             # Configuration settings
 ├── requirements.txt      # Python dependencies
 ├── start.sh             # Startup script
 ├── stop.sh              # Stop script
 ├── reset_db.py          # Database reset utility
 ├── templates/
 │   └── index.html       # Main dashboard template
 └── README.md           # This file
 ```

## 🔍 Troubleshooting

### Common Issues

1. **SNMP Connection Failed**
   - Verify PDU IP address in `config.py`
   - Check SNMP community string
   - Ensure network connectivity

 2. **No Data Displayed**
    - Check collector logs: `tail -f raritan_collector.log`
    - Verify SNMP OIDs are correct for your PDU model
    - Ensure PDU has power monitoring enabled

3. **Web Interface Not Loading**
   - Check web logs: `tail -f logs/web.log`
   - Verify port 5000 is not in use
   - Check firewall settings

 ### Log Files
 - **Collector Log**: `raritan_collector.log`
 - **Web Log**: `logs/web.log` (created by start.sh)
 - **Database**: `pdu_monitor.db`

## 🔄 API Endpoints

### Current Status
```
GET /api/current-status
```
Returns current PDU and port status

### Power Data
```
GET /api/power-data?period=hour&view=total
```
Returns power consumption data for charts

### Energy Data
```
GET /api/energy-data?period=day&view=total
```
Returns energy consumption data

### Port Management
```
GET /api/ports
POST /api/update-port-name
```
Port listing and name updates

### Data Export
```
GET /api/export-data?period=day&format=csv
```
Exports data as CSV

## 🎨 Customization

### UI Themes
The dashboard uses CSS custom properties for easy theming. Edit the `:root` section in `templates/index.html`:

```css
:root {
    --primary-color: #6366f1;
    --secondary-color: #10b981;
    --dark-bg: #0f172a;
    --card-bg: #1e293b;
    /* ... more variables */
}
```

### Chart Colors
Port colors are defined in the JavaScript:

```javascript
this.portColors = [
    '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    // ... add more colors as needed
];
```

## 📈 Performance

- **Data Collection**: ~1 second per collection cycle
- **Web Interface**: Sub-second response times
- **Database**: Optimized queries with proper indexing
- **Memory Usage**: Minimal memory footprint
- **Storage**: Efficient SQLite storage with automatic cleanup

## 🔒 Security

- **SNMP**: Uses community strings (consider SNMPv3 for production)
- **Web Interface**: No authentication (add if needed)
- **Database**: Local SQLite file
- **Network**: Only required ports (5000 for web, SNMP port for PDU)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs
3. Open an issue on GitHub
4. Include relevant log files and configuration

---

**Built for Raritan PDU PX3-5892** ⚡