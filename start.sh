#!/bin/bash

# PDU Power Monitoring System Startup Script for Debian/Linux
# This script starts both the web dashboard and data collector

echo "Starting PDU Power Monitoring System..."

# Check if Python3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3: sudo apt update && sudo apt install python3 python3-pip"
    exit 1
fi

# Check if pip3 is available
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is not installed"
    echo "Please install pip3: sudo apt install python3-pip"
    exit 1
fi

# Check if required packages are installed
echo "Checking dependencies..."
python3 -c "import flask, pysnmp, plotly, pandas" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing required packages..."
    pip3 install -r requirements.txt
fi

# Initialize database
echo "Initializing database..."
python3 -c "from app import create_app; app = create_app()" 2>/dev/null

# Start data collector in background
echo "Starting data collector..."
python3 scheduler.py &
COLLECTOR_PID=$!

# Wait a moment for collector to start
sleep 2

# Start web dashboard
echo "Starting web dashboard..."
echo "Dashboard will be available at: http://localhost:5000"
echo "Press Ctrl+C to stop both services"

# Function to cleanup on exit
cleanup() {
    echo "Shutting down services..."
    kill $COLLECTOR_PID 2>/dev/null
    wait $COLLECTOR_PID 2>/dev/null
    echo "Services stopped."
    exit 0
}

# Set trap for cleanup
trap cleanup SIGINT SIGTERM

# Start web dashboard
python3 app.py

# Cleanup if we get here
cleanup
