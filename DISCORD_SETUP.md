# Discord Webhook Setup Instructions

## 🔔 Discord Monthly Reports

The system now includes Discord webhook integration for monthly KWh reports!

### 📊 What You'll Receive

**Monthly Reports (1st of every month at midnight):**
- 📈 **Individual group reports** with device breakdown
- 🔌 **Per-device KWh consumption** within each group
- ⚡ **Group totals** and overall monthly consumption
- 📅 **Accurate timing** - reports at midnight (no extra hours)
- 🎨 **Beautiful Discord embeds** with color coding

### 🚀 Setup Instructions

#### Step 1: Install Dependencies
```bash
pip install schedule
```

#### Step 2: Configure .env File
Add your Discord webhook URL to your `.env` file:
```bash
DISCORD_WEBHOOK_URL=your_discord_webhook_url_here
```

#### Step 3: Test the Webhook
Test your Discord integration:
```bash
curl -X POST http://localhost:5000/api/discord/test
```

#### Step 4: Start Monthly Scheduler
Run the monthly scheduler (in addition to your main app):
```bash
python3 monthly_scheduler.py
```

### 🎯 API Endpoints

#### Test Discord Connection
```bash
POST /api/discord/test
```
Sends a test message to Discord to verify the webhook is working.

#### Manual Monthly Report
```bash
POST /api/discord/monthly-report
```
Manually trigger a monthly report (useful for testing).

### 📅 Scheduling

**Automatic Reports:**
- **When**: 1st of every month at midnight (00:00)
- **What**: Previous month's KWh consumption by group with device breakdown
- **Format**: Individual Discord embed per group + summary report

**Manual Testing:**
- Use the API endpoints to test anytime
- Check logs for confirmation of successful sends

### 🔒 Security Features

- **Webhook URL protected** in environment variables
- **No hardcoded credentials** in source code
- **Secure transmission** via HTTPS
- **Error handling** with detailed logging

### 📋 Example Monthly Reports

**Individual Group Report:**
```
📊 Servers Group - Monthly Report
December 2024 Power Consumption Breakdown

🔌 Device Breakdown
• Server 1: 89.45 kWh
• Server 2: 76.23 kWh
• Backup Server: 45.12 kWh

⚡ Group Total
**210.80 kWh**

Servers Group • January 1, 2025 at 00:00
```

**Summary Report:**
```
📊 Monthly Power Summary - December 2024
Total consumption across all groups

🔌 Servers Group
**210.80 kWh**

🔌 Network Equipment  
**89.23 kWh**

🔌 Development Lab
**156.89 kWh**

⚡ Total Monthly Consumption
**456.92 kWh**

Summary Report • January 1, 2025 at 00:00
```

### 🛠️ Troubleshooting

**Webhook Not Working:**
1. Check `.env` file has correct webhook URL
2. Verify Discord webhook is still active
3. Check application logs for errors
4. Test with `/api/discord/test` endpoint

**No Monthly Reports:**
1. Ensure `monthly_scheduler.py` is running
2. Check scheduler logs
3. Verify database has power data
4. Test manually with `/api/discord/monthly-report`

**Missing Data:**
1. Ensure groups are created and have outlets
2. Verify power data collection is working
3. Check database has readings for the month

### 🎉 Benefits

- **Automated reporting** - No manual work required
- **Group insights** - See consumption by equipment type
- **Historical tracking** - Monthly trends over time
- **Professional presentation** - Clean Discord embeds
- **Secure integration** - Protected webhook credentials
