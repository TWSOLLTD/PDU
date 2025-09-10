#!/usr/bin/env python3
"""
Monthly Discord Report Scheduler
Runs on the 1st of every month to send KWh reports
"""

import schedule
import time
import logging
from datetime import datetime
from flask import Flask
from discord_notifier import send_monthly_report

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    """Create Flask app for scheduler context"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/pdu_monitor.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    from models import db
    db.init_app(app)
    
    return app

def send_monthly_report_job():
    """Job function to send monthly report"""
    try:
        logger.info("Starting monthly Discord report job...")
        app = create_app()
        
        with app.app_context():
            success = send_monthly_report(app)
            
            if success:
                logger.info("Monthly Discord report sent successfully")
            else:
                logger.error("Failed to send monthly Discord report")
                
    except Exception as e:
        logger.error(f"Error in monthly report job: {str(e)}")

def main():
    """Main scheduler loop"""
    logger.info("Starting monthly Discord report scheduler...")
    
    # Schedule monthly report for 1st of every month at midnight
    schedule.every().month.do(send_monthly_report_job)
    
    # Also schedule a daily check to see if it's the 1st
    schedule.every().day.at("00:00").do(check_and_send_monthly_report)
    
    logger.info("Scheduler configured - monthly reports will be sent on the 1st of each month at midnight")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in scheduler: {str(e)}")
            time.sleep(60)

def check_and_send_monthly_report():
    """Check if today is the 1st and send report if needed"""
    today = datetime.now()
    
    if today.day == 1:
        logger.info(f"Today is the 1st of {today.strftime('%B %Y')} - sending monthly report")
        send_monthly_report_job()
    else:
        logger.debug(f"Today is {today.day} - not the 1st, skipping monthly report")

if __name__ == '__main__':
    main()
