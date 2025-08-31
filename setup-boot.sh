#!/bin/bash

# PDU Monitor Boot Setup Script
# This script sets up the PDU monitoring application to start on boot

echo "🔧 Setting up PDU Monitor to start on boot..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Define paths
SERVICE_FILE="pdu-monitor.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_FILE"
CURRENT_DIR=$(pwd)

echo "📁 Current directory: $CURRENT_DIR"
echo "📄 Service file: $SERVICE_FILE"

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Service file $SERVICE_FILE not found in current directory"
    exit 1
fi

# Copy service file to systemd directory
echo "📋 Copying service file to systemd directory..."
cp "$SERVICE_FILE" "$SERVICE_PATH"

if [ $? -eq 0 ]; then
    echo "✅ Service file copied successfully"
else
    echo "❌ Failed to copy service file"
    exit 1
fi

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

if [ $? -eq 0 ]; then
    echo "✅ Systemd daemon reloaded"
else
    echo "❌ Failed to reload systemd daemon"
    exit 1
fi

# Enable the service to start on boot
echo "🚀 Enabling service to start on boot..."
systemctl enable "$SERVICE_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Service enabled for boot startup"
else
    echo "❌ Failed to enable service"
    exit 1
fi

# Start the service now (optional)
read -p "🤔 Do you want to start the service now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "▶️ Starting PDU Monitor service..."
    systemctl start "$SERVICE_FILE"
    
    if [ $? -eq 0 ]; then
        echo "✅ Service started successfully"
        echo "📊 Check status with: systemctl status $SERVICE_FILE"
    else
        echo "❌ Failed to start service"
        echo "🔍 Check logs with: journalctl -u $SERVICE_FILE -f"
        exit 1
    fi
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📋 Service Management Commands:"
echo "   Start service:     sudo systemctl start $SERVICE_FILE"
echo "   Stop service:      sudo systemctl stop $SERVICE_FILE"
echo "   Restart service:   sudo systemctl restart $SERVICE_FILE"
echo "   Check status:      sudo systemctl status $SERVICE_FILE"
echo "   View logs:         sudo journalctl -u $SERVICE_FILE -f"
echo "   Disable boot:      sudo systemctl disable $SERVICE_FILE"
echo ""
echo "🌐 The web interface should be available at: http://localhost:5000"
echo "   (or your server's IP address on port 5000)"
echo ""
echo "📊 The service will start:"
echo "   - Data collector (scheduler.py)"
echo "   - Web dashboard (app.py)"
echo "   - Database initialization"
echo "   - Package dependency checks"
