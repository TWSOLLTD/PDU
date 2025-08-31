#!/usr/bin/env python3
"""
Data Processor for PDU Power Monitoring
Aggregates raw power readings into time-based summaries
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from models import db, PowerReading, PowerAggregation, PDU
import pandas as pd

logger = logging.getLogger(__name__)

class PowerDataProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_kwh(self, power_watts, duration_hours):
        """Calculate kWh from power (watts) and duration (hours)"""
        return (power_watts * duration_hours) / 1000.0
    
    def aggregate_hourly(self, start_time, end_time, pdu_id=None):
        """Aggregate data into hourly buckets"""
        try:
            # Build query
            query = db.session.query(
                func.strftime('%Y-%m-%d %H:00:00', PowerReading.timestamp).label('hour'),
                func.avg(PowerReading.power_watts).label('avg_power'),
                func.max(PowerReading.power_watts).label('max_power'),
                func.min(PowerReading.power_watts).label('min_power'),
                func.count(PowerReading.id).label('readings_count')
            ).filter(
                PowerReading.timestamp >= start_time,
                PowerReading.timestamp <= end_time
            )
            
            if pdu_id:
                query = query.filter(PowerReading.pdu_id == pdu_id)
            
            results = query.group_by('hour').order_by('hour').all()
            
            # Process results and calculate kWh
            aggregated_data = []
            for result in results:
                hour_start = datetime.strptime(result.hour, '%Y-%m-%d %H:00:00')
                hour_end = hour_start + timedelta(hours=1)
                
                # Calculate kWh (assuming readings are every minute, so 60 readings per hour)
                # If we have fewer readings, adjust accordingly
                duration_hours = min(result.readings_count / 60.0, 1.0)
                total_kwh = self.calculate_kwh(result.avg_power, duration_hours)
                
                aggregated_data.append({
                    'period_start': hour_start,
                    'period_end': hour_end,
                    'total_kwh': total_kwh,
                    'avg_power_watts': result.avg_power,
                    'max_power_watts': result.max_power,
                    'min_power_watts': result.min_power,
                    'readings_count': result.readings_count
                })
            
            return aggregated_data
            
        except Exception as e:
            self.logger.error(f"Error aggregating hourly data: {str(e)}")
            return []
    
    def aggregate_daily(self, start_time, end_time, pdu_id=None):
        """Aggregate data into daily buckets"""
        try:
            query = db.session.query(
                func.date(PowerReading.timestamp).label('day'),
                func.avg(PowerReading.power_watts).label('avg_power'),
                func.max(PowerReading.power_watts).label('max_power'),
                func.min(PowerReading.power_watts).label('min_power'),
                func.count(PowerReading.id).label('readings_count')
            ).filter(
                PowerReading.timestamp >= start_time,
                PowerReading.timestamp <= end_time
            )
            
            if pdu_id:
                query = query.filter(PowerReading.pdu_id == pdu_id)
            
            results = query.group_by('day').order_by('day').all()
            
            aggregated_data = []
            for result in results:
                day_start = datetime.strptime(result.day, '%Y-%m-%d')
                day_end = day_start + timedelta(days=1)
                
                # Calculate kWh (assuming readings every minute, so 1440 readings per day)
                duration_hours = min(result.readings_count / 60.0, 24.0)
                total_kwh = self.calculate_kwh(result.avg_power, duration_hours)
                
                aggregated_data.append({
                    'period_start': day_start,
                    'period_end': day_end,
                    'total_kwh': total_kwh,
                    'avg_power_watts': result.avg_power,
                    'max_power_watts': result.max_power,
                    'min_power_watts': result.min_power,
                    'readings_count': result.readings_count
                })
            
            return aggregated_data
            
        except Exception as e:
            self.logger.error(f"Error aggregating daily data: {str(e)}")
            return []
    
    def aggregate_monthly(self, start_time, end_time, pdu_id=None):
        """Aggregate data into monthly buckets"""
        try:
            query = db.session.query(
                func.strftime('%Y-%m', PowerReading.timestamp).label('month'),
                func.avg(PowerReading.power_watts).label('avg_power'),
                func.max(PowerReading.power_watts).label('max_power'),
                func.min(PowerReading.power_watts).label('min_power'),
                func.count(PowerReading.id).label('readings_count')
            ).filter(
                PowerReading.timestamp >= start_time,
                PowerReading.timestamp <= end_time
            )
            
            if pdu_id:
                query = query.filter(PowerReading.pdu_id == pdu_id)
            
            results = query.group_by('month').order_by('month').all()
            
            aggregated_data = []
            for result in results:
                month_start = datetime.strptime(result.month + '-01', '%Y-%m-%d')
                if month_start.month == 12:
                    month_end = datetime(month_start.year + 1, 1, 1)
                else:
                    month_end = datetime(month_start.year, month_start.month + 1, 1)
                
                # Calculate kWh (assuming readings every minute)
                # Get actual days in month for more accurate calculation
                days_in_month = (month_end - month_start).days
                duration_hours = min(result.readings_count / 60.0, days_in_month * 24.0)
                total_kwh = self.calculate_kwh(result.avg_power, duration_hours)
                
                aggregated_data.append({
                    'period_start': month_start,
                    'period_end': month_end,
                    'total_kwh': total_kwh,
                    'avg_power_watts': result.avg_power,
                    'max_power_watts': result.max_power,
                    'min_power_watts': result.min_power,
                    'readings_count': result.readings_count
                })
            
            return aggregated_data
            
        except Exception as e:
            self.logger.error(f"Error aggregating monthly data: {str(e)}")
            return []
    
    def get_power_summary(self, period='day', pdu_ids=None):
        """Get power consumption summary for specified period and PDUs"""
        try:
            end_time = datetime.utcnow()
            
            if period == 'day':
                start_time = end_time - timedelta(days=1)
                data = self.aggregate_hourly(start_time, end_time, pdu_ids)
            elif period == 'week':
                start_time = end_time - timedelta(days=7)
                data = self.aggregate_daily(start_time, end_time, pdu_ids)
            elif period == 'month':
                start_time = end_time - timedelta(days=30)
                data = self.aggregate_daily(start_time, end_time, pdu_ids)
            elif period == 'year':
                start_time = end_time - timedelta(days=365)
                data = self.aggregate_monthly(start_time, end_time, pdu_ids)
            else:
                raise ValueError(f"Unsupported period: {period}")
            
            return data
            
        except Exception as e:
            self.logger.error(f"Error getting power summary: {str(e)}")
            return []
    
    def store_aggregations(self, period_type, data, pdu_id=None):
        """Store aggregated data in the database"""
        try:
            for item in data:
                # Check if aggregation already exists
                existing = PowerAggregation.query.filter(
                    and_(
                        PowerAggregation.period_type == period_type,
                        PowerAggregation.period_start == item['period_start'],
                        PowerAggregation.pdu_id == pdu_id
                    )
                ).first()
                
                if existing:
                    # Update existing record
                    existing.total_kwh = item['total_kwh']
                    existing.avg_power_watts = item['avg_power_watts']
                    existing.max_power_watts = item['max_power_watts']
                    existing.min_power_watts = item['min_power_watts']
                else:
                    # Create new record
                    aggregation = PowerAggregation(
                        pdu_id=pdu_id,
                        period_type=period_type,
                        period_start=item['period_start'],
                        period_end=item['period_end'],
                        total_kwh=item['total_kwh'],
                        avg_power_watts=item['avg_power_watts'],
                        max_power_watts=item['max_power_watts'],
                        min_power_watts=item['min_power_watts']
                    )
                    db.session.add(aggregation)
            
            db.session.commit()
            self.logger.info(f"Stored {len(data)} {period_type} aggregations")
            
        except Exception as e:
            self.logger.error(f"Error storing aggregations: {str(e)}")
            db.session.rollback()

def main():
    """Test function"""
    processor = PowerDataProcessor()
    
    # Test aggregation
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=1)
    
    print("Testing hourly aggregation...")
    hourly_data = processor.aggregate_hourly(start_time, end_time)
    print(f"Found {len(hourly_data)} hourly buckets")
    
    print("Testing daily aggregation...")
    daily_data = processor.aggregate_daily(start_time, end_time)
    print(f"Found {len(daily_data)} daily buckets")

if __name__ == "__main__":
    main()

