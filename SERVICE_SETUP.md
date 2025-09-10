# PDU Monitoring Service Setup Guide

## 🚀 Systemd Service Installation

The PDU monitoring system is now packaged as a systemd service for easy management!

### 📋 What's Included

- **Integrated Service**: Web app + Discord scheduler in one service
- **Systemd Management**: Use `systemctl` commands for control
- **Auto-start**: Service can start automatically on boot
- **Logging**: Centralized logging via journald
- **Security**: Protected webhook URLs in `.env` only

### 🔧 Installation Steps

#### Step 1: Install the Service
```bash
# Make installation script executable
chmod +x install_service.sh

# Run installation (as root)
sudo ./install_service.sh
```

#### Step 2: Configure Environment
```bash
# Create .env file from template
cp env_template.txt .env

# Edit with your actual credentials
nano .env
```

**Required .env entries:**
```
SNMP_USERNAME=snmpuser
SNMP_AUTH_PASSWORD=your_snmp_auth_password_here
SNMP_PRIV_PASSWORD=your_snmp_priv_password_here
PDU_IP=172.0.250.9
GROUP_MANAGEMENT_PASSWORD=your_group_password_here
DISCORD_WEBHOOK_URL=your_discord_webhook_url_here
```

#### Step 3: Start the Service
```bash
# Start the service
sudo systemctl start pdu-monitor

# Check status
sudo systemctl status pdu-monitor

# Enable auto-start on boot
sudo systemctl enable pdu-monitor
```

### 🎮 Service Management

#### Using systemctl (Standard)
```bash
# Start service
sudo systemctl start pdu-monitor

# Stop service
sudo systemctl stop pdu-monitor

# Restart service
sudo systemctl restart pdu-monitor

# Check status
sudo systemctl status pdu-monitor

# Enable auto-start
sudo systemctl enable pdu-monitor

# Disable auto-start
sudo systemctl disable pdu-monitor

# View logs
sudo journalctl -u pdu-monitor -f
```

#### Using Service Manager Script (Convenient)
```bash
# Make script executable
chmod +x service_manager.sh

# Start service
./service_manager.sh start

# Check status
./service_manager.sh status

# View logs
./service_manager.sh logs

# Test Discord webhook
./service_manager.sh test-discord

# Test monthly report
./service_manager.sh test-monthly
```

### 🔍 Monitoring & Testing

#### Check Service Status
```bash
sudo systemctl status pdu-monitor
```

#### View Live Logs
```bash
sudo journalctl -u pdu-monitor -f
```

#### Test Discord Integration
```bash
# Test webhook connection
curl -X POST http://localhost:5000/api/discord/test

# Test monthly report
curl -X POST http://localhost:5000/api/discord/monthly-report
```

#### Access Web Interface
- **URL**: `http://your-server-ip:5000`
- **Local**: `http://localhost:5000`

### 📊 What the Service Does

**Automatically:**
- ✅ **Data Collection**: SNMP power readings every 60 seconds
- ✅ **Web Interface**: Serves the monitoring dashboard
- ✅ **Discord Reports**: Monthly KWh reports on 1st at midnight
- ✅ **Database Management**: Stores all power consumption data
- ✅ **Logging**: Comprehensive logging to journald

**Manual Testing:**
- 🔔 **Discord Test**: Verify webhook connection
- 📊 **Monthly Report**: Send test monthly report
- 🌐 **Web Interface**: Access monitoring dashboard

### 🛠️ Troubleshooting

#### Service Won't Start
```bash
# Check service status
sudo systemctl status pdu-monitor

# View detailed logs
sudo journalctl -u pdu-monitor --no-pager

# Check .env file exists and has correct values
ls -la .env
cat .env
```

#### Discord Not Working
```bash
# Test webhook
./service_manager.sh test-discord

# Check webhook URL in .env
grep DISCORD_WEBHOOK_URL .env
```

#### Database Issues
```bash
# Check database file
ls -la instance/pdu_monitor.db

# Check database permissions
ls -la instance/
```

#### Port Already in Use
```bash
# Check what's using port 5000
sudo netstat -tlnp | grep :5000

# Kill existing process if needed
sudo pkill -f "python.*app.py"
```

### 🔒 Security Features

- **Environment Variables**: All secrets in `.env` file
- **File Permissions**: Service runs with appropriate permissions
- **Systemd Security**: Protected system directories
- **Logging**: All activity logged to journald
- **No Hardcoded Secrets**: Webhook URL only in `.env`

### 📈 Performance

- **Memory Limit**: 512MB maximum
- **File Descriptors**: 65536 limit
- **Restart Policy**: Automatic restart on failure
- **Resource Protection**: System directories protected

### 🎯 Benefits

- **Easy Management**: Standard systemd commands
- **Auto-start**: Starts automatically on boot
- **Reliability**: Automatic restart on failure
- **Logging**: Centralized logging system
- **Security**: Protected configuration
- **Integration**: Web app + Discord scheduler in one service

### 🚀 Quick Start Commands

```bash
# Install service
sudo ./install_service.sh

# Configure environment
cp env_template.txt .env
nano .env

# Start service
sudo systemctl start pdu-monitor

# Enable auto-start
sudo systemctl enable pdu-monitor

# Test Discord
./service_manager.sh test-discord
```

Your PDU monitoring system is now running as a professional systemd service! 🎉
