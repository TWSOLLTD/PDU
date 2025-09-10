# Security Setup Instructions

## 🔒 Securing SNMP Credentials

The SNMP credentials have been moved to environment variables for security. Follow these steps to set up your `.env` file:

### Step 1: Create .env file
Copy the template file and create your `.env` file:

```bash
cp env_template.txt .env
```

### Step 2: Edit .env file
Edit the `.env` file with your actual credentials:

```bash
nano .env
```

Update the following values:
```
SNMP_USERNAME=snmpuser
SNMP_AUTH_PASSWORD=your_snmp_auth_password_here
SNMP_PRIV_PASSWORD=your_snmp_priv_password_here
PDU_IP=172.0.250.9
GROUP_MANAGEMENT_PASSWORD=Ru5tyt1n#
DISCORD_WEBHOOK_URL=your_discord_webhook_url_here
```

### Step 3: Secure the .env file
Set proper permissions on the `.env` file:

```bash
chmod 600 .env
```

### Step 4: Verify .env is in .gitignore
Ensure the `.env` file is listed in `.gitignore` to prevent accidental commits:

```bash
echo ".env" >> .gitignore
```

## ✅ Security Benefits

- **No hardcoded credentials** in source code
- **Environment variables** keep secrets separate from code
- **Gitignore protection** prevents accidental commits
- **File permissions** restrict access to root only
- **Fallback values** maintain functionality if env vars missing

## 🚨 Important Notes

- **NEVER commit the `.env` file** to version control
- **Keep the `.env` file secure** with proper permissions
- **Use strong passwords** for all credentials
- **Regularly rotate credentials** for enhanced security

## 🔧 Troubleshooting

If the application fails to start after these changes:

1. Check that `.env` file exists and has correct permissions
2. Verify all required environment variables are set
3. Check application logs for missing environment variable errors
4. Ensure `python-dotenv` package is installed: `pip install python-dotenv`
