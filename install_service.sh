#!/bin/bash
# PDU Monitoring Service Installation Script

set -e

echo "🔧 Installing TWSOL PDU Monitoring Service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Set variables
SERVICE_NAME="pdu-monitor"
SERVICE_FILE="pdu-monitor.service"
INSTALL_DIR="/opt/PDU-NEW"
SYSTEMD_DIR="/etc/systemd/system"

echo "📁 Setting up directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/instance"

echo "📋 Copying service files..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/"
cp "pdu_service.py" "$INSTALL_DIR/"

echo "🔧 Setting permissions..."
chmod +x "$INSTALL_DIR/pdu_service.py"
chmod 644 "$SYSTEMD_DIR/$SERVICE_FILE"
chown -R root:root "$INSTALL_DIR"

echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

echo "🔄 Reloading systemd..."
systemctl daemon-reload

echo "✅ Service installed successfully!"
echo ""
echo "🚀 Service Management Commands:"
echo "  Start:   systemctl start $SERVICE_NAME"
echo "  Stop:    systemctl stop $SERVICE_NAME"
echo "  Status:  systemctl status $SERVICE_NAME"
echo "  Enable:  systemctl enable $SERVICE_NAME"
echo "  Disable: systemctl disable $SERVICE_NAME"
echo "  Logs:    journalctl -u $SERVICE_NAME -f"
echo ""
echo "📝 Next Steps:"
echo "1. Create your .env file:"
echo "   cp env_template.txt .env"
echo "   nano .env"
echo ""
echo "2. Start the service:"
echo "   systemctl start $SERVICE_NAME"
echo ""
echo "3. Enable auto-start:"
echo "   systemctl enable $SERVICE_NAME"
echo ""
echo "4. Check status:"
echo "   systemctl status $SERVICE_NAME"
echo ""
echo "🎉 Installation complete!"
