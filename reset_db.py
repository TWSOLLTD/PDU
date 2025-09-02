#!/usr/bin/env python3
"""
Database Reset Script for Raritan PDU
Resets the database and recreates it with 36 ports
"""

import os
import sys
from models import db, PDU, PDUPort, init_db

def reset_database():
    """Reset the database and recreate with 36 ports"""
    try:
        # Remove existing database file
        db_file = 'pdu_monitor.db'
        if os.path.exists(db_file):
            os.remove(db_file)
            print(f"Removed existing database: {db_file}")
        
        # Initialize new database
        print("Initializing new database with 36 ports...")
        init_db()
        
        # Verify the setup
        with db.app.app_context():
            pdu = PDU.query.first()
            if pdu:
                ports = PDUPort.query.filter_by(pdu_id=pdu.id).all()
                print(f"✅ Database reset successful!")
                print(f"   PDU: {pdu.name} ({pdu.ip_address})")
                print(f"   Ports: {len(ports)} ports created")
                print(f"   Port range: {ports[0].port_number} to {ports[-1].port_number}")
            else:
                print("❌ Error: No PDU found after reset")
                
    except Exception as e:
        print(f"❌ Error resetting database: {str(e)}")
        return False
    
    return True

if __name__ == '__main__':
    print("🔄 Raritan PDU Database Reset Tool")
    print("This will delete the existing database and recreate it with 36 ports.")
    print()
    
    response = input("Are you sure you want to continue? (y/N): ")
    if response.lower() in ['y', 'yes']:
        if reset_database():
            print("\n✅ Database reset completed successfully!")
            print("You can now start the system with: ./start.sh")
        else:
            print("\n❌ Database reset failed!")
            sys.exit(1)
    else:
        print("Database reset cancelled.")
