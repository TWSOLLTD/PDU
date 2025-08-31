#!/usr/bin/env python3
"""
Webhook Handler for GitHub Auto-Deployment
Receives push notifications from GitHub and automatically updates the server
"""

from flask import Flask, request, jsonify
import subprocess
import os
import logging
import hmac
import hashlib
from config import WEBHOOK_SECRET

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def verify_signature(payload_body, signature, secret):
    """Verify GitHub webhook signature"""
    if not signature:
        return False
    
    # Remove 'sha256=' prefix
    if signature.startswith('sha256='):
        signature = signature[7:]
    
    # Calculate expected signature
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

@app.route('/webhook/update', methods=['POST'])
def update_webhook():
    """Handle GitHub webhook for automatic deployment"""
    try:
        # Get the raw payload
        payload_body = request.get_data()
        
        # Verify GitHub signature if secret is configured
        if WEBHOOK_SECRET:
            signature = request.headers.get('X-Hub-Signature-256')
            if not verify_signature(payload_body, signature, WEBHOOK_SECRET):
                logger.warning("Invalid webhook signature")
                return jsonify({'status': 'error', 'message': 'Invalid signature'}), 401
        
        # Check if it's a push event
        event_type = request.headers.get('X-GitHub-Event')
        if event_type != 'push':
            logger.info(f"Ignoring non-push event: {event_type}")
            return jsonify({'status': 'ignored', 'message': f'Event type: {event_type}'}), 200
        
        # Check if it's to the main branch
        payload = request.get_json()
        if payload.get('ref') != 'refs/heads/main':
            logger.info("Ignoring push to non-main branch")
            return jsonify({'status': 'ignored', 'message': 'Not main branch'}), 200
        
        logger.info("🚀 Starting automatic deployment...")
        
        # Change to project directory
        project_dir = '/opt/PDU-NEW'
        if not os.path.exists(project_dir):
            return jsonify({'status': 'error', 'message': 'Project directory not found'}), 500
        
        # Pull latest changes
        logger.info("📥 Pulling latest changes...")
        result = subprocess.run(
            ['git', 'pull', 'origin', 'main'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Git pull output: {result.stdout}")
        
        # Activate virtual environment and update dependencies
        logger.info("🐍 Updating dependencies...")
        result = subprocess.run(
            ['bash', '-c', 'source pdu_env/bin/activate && pip install -r requirements.txt'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Pip install output: {result.stdout}")
        
        # Restart services
        logger.info("🔄 Restarting services...")
        subprocess.run(['systemctl', 'restart', 'pdu-collector'], check=True)
        subprocess.run(['systemctl', 'restart', 'pdu-dashboard'], check=True)
        
        logger.info("✅ Deployment completed successfully!")
        return jsonify({
            'status': 'success',
            'message': 'Deployment completed successfully',
            'git_output': result.stdout
        })
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Command failed: {e.cmd}, Return code: {e.returncode}, Output: {e.stdout}, Error: {e.stderr}"
        logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@app.route('/webhook/status', methods=['GET'])
def webhook_status():
    """Check webhook handler status"""
    return jsonify({
        'status': 'running',
        'message': 'Webhook handler is active',
        'endpoint': '/webhook/update'
    })

if __name__ == '__main__':
    logger.info("Starting webhook handler...")
    app.run(host='0.0.0.0', port=5001, debug=False)
