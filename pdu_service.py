#!/usr/bin/env python3
"""
PDU Monitoring Service
Integrated service that runs both the web app and Discord scheduler
"""

import os
import sys
import time
import signal
import threading
import logging
from datetime import datetime
from flask import Flask
import schedule

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATABASE_URI, FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from models import db, init_db
from snmp_collector import collect_power_data
from discord_notifier import send_monthly_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/PDU-NEW/pdu_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PDUMonitoringService:
    def __init__(self):
        self.app = None
        self.data_collection_thread = None
        self.scheduler_thread = None
        self.running = False
        
    def create_app(self):
        """Create Flask app"""
        # Import the main app with all routes
        from app import app
        
        # Initialize database
        with app.app_context():
            init_db()
            logger.info("Database initialized successfully")
        
        return app
    
    def data_collection_worker(self):
        """Background data collection worker"""
        logger.info("Starting data collection worker...")
        
        while self.running:
            try:
                logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Collecting power data...")
                collect_power_data(self.app)
                logger.info("Data collection completed")
            except Exception as e:
                logger.error(f"Error in data collection: {str(e)}")
            
            # Wait 60 seconds before next collection
            for _ in range(60):
                if not self.running:
                    break
                time.sleep(1)
        
        logger.info("Data collection worker stopped")
    
    def scheduler_worker(self):
        """Discord scheduler worker"""
        logger.info("Starting Discord scheduler worker...")
        
        # Schedule monthly report for 1st of every month at midnight
        schedule.every().month.do(self.send_monthly_report_job)
        
        # Also schedule a daily check to see if it's the 1st
        schedule.every().day.at("00:00").do(self.check_and_send_monthly_report)
        
        logger.info("Scheduler configured - monthly reports will be sent on the 1st of each month at midnight")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler: {str(e)}")
                time.sleep(60)
        
        logger.info("Scheduler worker stopped")
    
    def send_monthly_report_job(self):
        """Job function to send monthly report"""
        try:
            logger.info("Starting monthly Discord report job...")
            
            with self.app.app_context():
                success = send_monthly_report(self.app)
                
                if success:
                    logger.info("Monthly Discord report sent successfully")
                else:
                    logger.error("Failed to send monthly Discord report")
                    
        except Exception as e:
            logger.error(f"Error in monthly report job: {str(e)}")
    
    def check_and_send_monthly_report(self):
        """Check if today is the 1st and send report if needed"""
        today = datetime.now()
        
        if today.day == 1:
            logger.info(f"Today is the 1st of {today.strftime('%B %Y')} - sending monthly report")
            self.send_monthly_report_job()
        else:
            logger.debug(f"Today is {today.day} - not the 1st, skipping monthly report")
    
    def start(self):
        """Start the service"""
        logger.info("Starting PDU Monitoring Service...")
        
        try:
            # Create Flask app
            self.app = self.create_app()
            
            # Set running flag
            self.running = True
            
            # Start data collection thread
            self.data_collection_thread = threading.Thread(target=self.data_collection_worker, daemon=True)
            self.data_collection_thread.start()
            
            # Start scheduler thread
            self.scheduler_thread = threading.Thread(target=self.scheduler_worker, daemon=True)
            self.scheduler_thread.start()
            
            logger.info("PDU Monitoring Service started successfully")
            logger.info(f"Web interface available at: http://{FLASK_HOST}:{FLASK_PORT}")
            logger.info("Data collection running every 60 seconds")
            logger.info("Discord monthly reports scheduled for 1st of each month at midnight")
            
            # Start Flask app (this blocks)
            self.app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)
            
        except Exception as e:
            logger.error(f"Error starting service: {str(e)}")
            self.stop()
            raise
    
    def stop(self):
        """Stop the service"""
        logger.info("Stopping PDU Monitoring Service...")
        
        self.running = False
        
        # Wait for threads to finish
        if self.data_collection_thread and self.data_collection_thread.is_alive():
            self.data_collection_thread.join(timeout=5)
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        logger.info("PDU Monitoring Service stopped")

# Global service instance
service = PDUMonitoringService()

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    service.stop()
    sys.exit(0)

def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        service.start()
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service failed: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
