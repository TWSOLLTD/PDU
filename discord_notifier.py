#!/usr/bin/env python3
"""
Discord Webhook Notification System
Sends monthly KWh reports to Discord via webhook
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from flask import Flask
from config import DISCORD_WEBHOOK_URL
from models import db, OutletGroup, PortPowerReading, PDUPort

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self, app=None):
        self.app = app
        self.webhook_url = DISCORD_WEBHOOK_URL
        
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured - notifications disabled")
    
    def send_monthly_report(self):
        """Send monthly KWh report for all groups - one message per group"""
        if not self.webhook_url:
            logger.warning("Discord webhook not configured - skipping monthly report")
            return False
        
        try:
            with self.app.app_context():
                # Get current month data
                now = datetime.now()
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                
                # Calculate previous month (since we're sending on 1st of current month)
                if now.month == 1:
                    prev_month_start = now.replace(year=now.year-1, month=12, day=1)
                    prev_month_end = now.replace(day=1) - timedelta(days=1)
                else:
                    prev_month_start = now.replace(month=now.month-1, day=1)
                    prev_month_end = now.replace(day=1) - timedelta(days=1)
                
                # Get all groups
                groups = OutletGroup.query.all()
                
                if not groups:
                    logger.info("No groups found for monthly report")
                    return True
                
                success_count = 0
                
                # Send individual report for each group
                for group in groups:
                    if self.send_group_monthly_report(group, prev_month_start, prev_month_end, now):
                        success_count += 1
                
                # Send summary report
                if success_count > 0:
                    self.send_summary_report(groups, prev_month_start, prev_month_end, now)
                
                logger.info(f"Sent {success_count} group reports and 1 summary report")
                return success_count > 0
                    
        except Exception as e:
            logger.error(f"Error sending Discord monthly report: {str(e)}")
            return False
    
    def send_group_monthly_report(self, group, month_start, month_end, now):
        """Send individual monthly report for a specific group"""
        try:
            # Calculate group KWh and device breakdown
            group_data = self.calculate_group_detailed_kwh(group, month_start, month_end)
            
            if group_data['total_kwh'] == 0:
                logger.info(f"Group {group.name} has no power consumption data")
                return True
            
            # Build Discord embed for this group
            embed = {
                "title": f"📊 {group.name} - Monthly Report",
                "description": f"**{month_start.strftime('%B %Y')}** Power Consumption Breakdown",
                "color": 0x0099ff,  # Blue color
                "timestamp": now.isoformat(),
                "fields": []
            }
            
            # Add device breakdown
            device_text = ""
            for device in group_data['devices']:
                device_text += f"• **{device['name']}**: {device['kwh']:.2f} kWh\n"
            
            embed["fields"].append({
                "name": "🔌 Device Breakdown",
                "value": device_text or "No devices with power consumption",
                "inline": False
            })
            
            # Add group total
            embed["fields"].append({
                "name": "⚡ **Group Total**",
                "value": f"**{group_data['total_kwh']:.2f} kWh**",
                "inline": False
            })
            
            # Add footer
            embed["footer"] = {
                "text": f"{group.name} • {now.strftime('%B %d, %Y at %H:%M')}",
                "icon_url": "https://cdn.discordapp.com/embed/avatars/0.png"
            }
            
            # Send to Discord
            payload = {
                "username": "TWSOL Power Monitor",
                "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
                "embeds": [embed]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 204:
                logger.info(f"Group report sent successfully for {group.name}")
                return True
            else:
                logger.error(f"Discord webhook failed for group {group.name}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending group report for {group.name}: {str(e)}")
            return False
    
    def send_summary_report(self, groups, month_start, month_end, now):
        """Send summary report with all groups"""
        try:
            embed = {
                "title": f"📊 Monthly Power Summary - {month_start.strftime('%B %Y')}",
                "description": f"Total consumption across all groups",
                "color": 0x00ff00,  # Green color
                "timestamp": now.isoformat(),
                "fields": []
            }
            
            total_monthly_kwh = 0
            
            for group in groups:
                group_data = self.calculate_group_detailed_kwh(group, month_start, month_end)
                total_monthly_kwh += group_data['total_kwh']
                
                # Add group summary field
                embed["fields"].append({
                    "name": f"🔌 {group.name}",
                    "value": f"**{group_data['total_kwh']:.2f} kWh**",
                    "inline": True
                })
            
            # Add total field
            embed["fields"].append({
                "name": "⚡ **Total Monthly Consumption**",
                "value": f"**{total_monthly_kwh:.2f} kWh**",
                "inline": False
            })
            
            # Add footer
            embed["footer"] = {
                "text": f"Summary Report • {now.strftime('%B %d, %Y at %H:%M')}",
                "icon_url": "https://cdn.discordapp.com/embed/avatars/0.png"
            }
            
            # Send to Discord
            payload = {
                "username": "TWSOL Power Monitor",
                "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
                "embeds": [embed]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 204:
                logger.info("Summary report sent successfully")
                return True
            else:
                logger.error(f"Discord summary webhook failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending summary report: {str(e)}")
            return False
    
    def calculate_group_detailed_kwh(self, group, month_start, month_end):
        """Calculate detailed KWh for a group with device breakdown"""
        try:
            outlet_ids = group.get_outlet_ids()
            if not outlet_ids:
                return {'total_kwh': 0.0, 'devices': []}
            
            devices = []
            total_kwh = 0.0
            
            for outlet_id in outlet_ids:
                # Get outlet info
                outlet = PDUPort.query.get(outlet_id)
                if not outlet:
                    continue
                
                # Get all power readings for this outlet in the month
                readings = PortPowerReading.query.filter(
                    PortPowerReading.port_id == outlet_id,
                    PortPowerReading.timestamp >= month_start,
                    PortPowerReading.timestamp <= month_end
                ).order_by(PortPowerReading.timestamp).all()
                
                if len(readings) < 2:
                    continue
                
                device_kwh = 0.0
                
                # Calculate KWh by integrating power over time
                for i in range(1, len(readings)):
                    prev_reading = readings[i-1]
                    curr_reading = readings[i]
                    
                    # Time difference in hours
                    time_diff = (curr_reading.timestamp - prev_reading.timestamp).total_seconds() / 3600
                    
                    # Average power during this period (in kW)
                    avg_power_kw = (prev_reading.power_kw + curr_reading.power_kw) / 2
                    
                    # Energy consumed (kWh)
                    energy_kwh = avg_power_kw * time_diff
                    device_kwh += energy_kwh
                
                if device_kwh > 0:
                    devices.append({
                        'name': outlet.name or f'Outlet {outlet.port_number}',
                        'port_number': outlet.port_number,
                        'kwh': device_kwh
                    })
                    total_kwh += device_kwh
            
            return {
                'total_kwh': total_kwh,
                'devices': devices
            }
            
        except Exception as e:
            logger.error(f"Error calculating detailed KWh for group {group.name}: {str(e)}")
            return {'total_kwh': 0.0, 'devices': []}
    
    def calculate_group_monthly_kwh(self, group, month_start, month_end):
        """Calculate total KWh for a group in a given month (legacy function)"""
        detailed_data = self.calculate_group_detailed_kwh(group, month_start, month_end)
        return detailed_data['total_kwh']
    
    def send_test_message(self):
        """Send a test message to Discord"""
        if not self.webhook_url:
            logger.warning("Discord webhook not configured - cannot send test message")
            return False
        
        try:
            payload = {
                "username": "TWSOL Power Monitor",
                "content": "🔧 **Test Message** - Discord webhook is working correctly!",
                "embeds": [{
                    "title": "✅ Connection Test",
                    "description": "Discord notifications are properly configured",
                    "color": 0x00ff00,
                    "timestamp": datetime.now().isoformat()
                }]
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 204:
                logger.info("Discord test message sent successfully")
                return True
            else:
                logger.error(f"Discord test failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Discord test message: {str(e)}")
            return False

def send_monthly_report(app):
    """Function to send monthly report - called by scheduler"""
    notifier = DiscordNotifier(app)
    return notifier.send_monthly_report()

def send_test_notification(app):
    """Function to send test notification"""
    notifier = DiscordNotifier(app)
    return notifier.send_test_message()
