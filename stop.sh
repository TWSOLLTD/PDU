#!/bin/bash

# Raritan PDU Power Monitoring System Stop Script

echo "Stopping Raritan PDU Power Monitoring System..."

# Stop data collector
if [ -f collector.pid ]; then
    COLLECTOR_PID=$(cat collector.pid)
    if kill -0 $COLLECTOR_PID 2>/dev/null; then
        echo "Stopping data collector (PID: $COLLECTOR_PID)..."
        kill $COLLECTOR_PID
        rm collector.pid
    else
        echo "Data collector not running"
        rm collector.pid
    fi
else
    echo "No collector PID file found"
fi

# Stop web interface
if [ -f web.pid ]; then
    WEB_PID=$(cat web.pid)
    if kill -0 $WEB_PID 2>/dev/null; then
        echo "Stopping web interface (PID: $WEB_PID)..."
        kill $WEB_PID
        rm web.pid
    else
        echo "Web interface not running"
        rm web.pid
    fi
else
    echo "No web PID file found"
fi

echo "System stopped successfully!"
