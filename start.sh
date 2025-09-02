#!/bin/bash

# Raritan PDU Power Monitoring System Startup Script

echo "Starting Raritan PDU Power Monitoring System..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is not installed"
    exit 1
fi

# Check if required packages are installed
echo "Checking dependencies..."
python3 -c "import flask, easysnmp, plotly" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing required packages..."
    pip3 install -r requirements.txt
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Start the data collector in the background
echo "Starting SNMP data collector..."
python3 snmp_collector.py > logs/collector.log 2>&1 &
COLLECTOR_PID=$!

# Wait a moment for the collector to initialize
sleep 2

# Start the web interface
echo "Starting web interface..."
python3 app.py > logs/web.log 2>&1 &
WEB_PID=$!

# Save PIDs for later cleanup
echo $COLLECTOR_PID > collector.pid
echo $WEB_PID > web.pid

echo "System started successfully!"
echo "Data collector PID: $COLLECTOR_PID"
echo "Web interface PID: $WEB_PID"
echo "Web interface available at: http://localhost:5000"
echo ""
echo "To stop the system, run: ./stop.sh"
echo "To view logs: tail -f logs/collector.log logs/web.log"
