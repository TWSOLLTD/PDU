#!/usr/bin/env python3
"""
PDU Data Collection Scheduler
Automatically collects power consumption data from PDUs at regular intervals
"""

import time
import logging
import signal
import sys
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import COLLECTION_INTERVAL
from snmp_collector import PDUCollector
from models import db, init_db
from data_processor import PowerDataProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdu_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PDUScheduler:
    def __init__(self):
        self.scheduler = BlockingScheduler()
        self.collector = PDUCollector()
        self.data_processor = PowerDataProcessor()
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        self.scheduler.shutdown()
        sys.exit(0)
    
    def collect_data(self):
        """Collect data from all PDUs"""
        try:
            logger.info("Starting scheduled data collection...")
            self.collector.collect_all_pdus()
            logger.info("Data collection completed successfully")
            
            # Process and store aggregations
            self.process_aggregations()
            
        except Exception as e:
            logger.error(f"Error during data collection: {str(e)}")
    
    def process_aggregations(self):
        """Process and store data aggregations"""
        try:
            logger.info("Processing data aggregations...")
            
            # Get all PDU IDs
            from models import PDU
            pdus = PDU.query.all()
            pdu_ids = [pdu.id for pdu in pdus]
            
            # Process different time periods
            periods = ['hourly', 'daily', 'monthly']
            
            for period in periods:
                try:
                    if period == 'hourly':
                        # Process last 24 hours
                        end_time = datetime.utcnow()
                        start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
                        data = self.data_processor.aggregate_hourly(start_time, end_time)
                    elif period == 'daily':
                        # Process last 30 days
                        end_time = datetime.utcnow()
                        start_time = end_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        data = self.data_processor.aggregate_daily(start_time, end_time)
                    elif period == 'monthly':
                        # Process last 12 months
                        end_time = datetime.utcnow()
                        start_time = end_time.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                        data = self.data_processor.aggregate_monthly(start_time, end_time)
                    
                    # Store aggregations for each PDU and combined
                    for pdu_id in pdu_ids:
                        self.data_processor.store_aggregations(period, data, pdu_id)
                    
                    # Store combined aggregations
                    self.data_processor.store_aggregations(period, data, None)
                    
                    logger.info(f"Processed {period} aggregations")
                    
                except Exception as e:
                    logger.error(f"Error processing {period} aggregations: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Error processing aggregations: {str(e)}")
    
    def start(self):
        """Start the scheduler"""
        try:
            # Initialize database
            with app.app_context():
                init_db()
                logger.info("Database initialized successfully")
            
            # Add job to collect data every minute
            self.scheduler.add_job(
                func=self.collect_data,
                trigger=IntervalTrigger(seconds=COLLECTION_INTERVAL),
                id='pdu_data_collection',
                name='PDU Data Collection',
                max_instances=1,
                replace_existing=True
            )
            
            logger.info(f"Starting PDU data collection scheduler (interval: {COLLECTION_INTERVAL} seconds)")
            logger.info("Press Ctrl+C to stop the scheduler")
            
            # Start the scheduler
            self.scheduler.start()
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {str(e)}")
            sys.exit(1)

def main():
    """Main function"""
    try:
        scheduler = PDUScheduler()
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Import Flask app context
    from app import create_app
    app = create_app()
    
    main()
