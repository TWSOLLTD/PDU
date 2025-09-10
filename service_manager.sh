#!/bin/bash
# PDU Monitoring Service Management Script

SERVICE_NAME="pdu-monitor"

case "$1" in
    start)
        echo "🚀 Starting PDU Monitoring Service..."
        systemctl start "$SERVICE_NAME"
        systemctl status "$SERVICE_NAME" --no-pager
        ;;
    stop)
        echo "🛑 Stopping PDU Monitoring Service..."
        systemctl stop "$SERVICE_NAME"
        systemctl status "$SERVICE_NAME" --no-pager
        ;;
    restart)
        echo "🔄 Restarting PDU Monitoring Service..."
        systemctl restart "$SERVICE_NAME"
        systemctl status "$SERVICE_NAME" --no-pager
        ;;
    status)
        echo "📊 PDU Monitoring Service Status:"
        systemctl status "$SERVICE_NAME" --no-pager
        ;;
    enable)
        echo "✅ Enabling PDU Monitoring Service (auto-start)..."
        systemctl enable "$SERVICE_NAME"
        echo "Service will start automatically on boot"
        ;;
    disable)
        echo "❌ Disabling PDU Monitoring Service (auto-start)..."
        systemctl disable "$SERVICE_NAME"
        echo "Service will NOT start automatically on boot"
        ;;
    logs)
        echo "📋 Showing PDU Monitoring Service logs (Ctrl+C to exit):"
        journalctl -u "$SERVICE_NAME" -f
        ;;
    test-discord)
        echo "🔔 Testing Discord webhook..."
        curl -X POST http://localhost:5000/api/discord/test
        echo ""
        ;;
    test-monthly)
        echo "📊 Testing monthly Discord report..."
        curl -X POST http://localhost:5000/api/discord/monthly-report
        echo ""
        ;;
    *)
        echo "🔧 PDU Monitoring Service Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|enable|disable|logs|test-discord|test-monthly}"
        echo ""
        echo "Commands:"
        echo "  start         - Start the service"
        echo "  stop          - Stop the service"
        echo "  restart       - Restart the service"
        echo "  status        - Show service status"
        echo "  enable        - Enable auto-start on boot"
        echo "  disable       - Disable auto-start on boot"
        echo "  logs          - Show live logs (Ctrl+C to exit)"
        echo "  test-discord  - Test Discord webhook connection"
        echo "  test-monthly  - Send test monthly report"
        echo ""
        echo "Examples:"
        echo "  $0 start"
        echo "  $0 status"
        echo "  $0 logs"
        echo "  $0 test-discord"
        exit 1
        ;;
esac
