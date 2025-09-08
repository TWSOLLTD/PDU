#!/usr/bin/env python3
"""
Database Reset Script for Raritan PX3-5892 Outlet Monitor
Resets the database and recreates it with 36 outlets and new features
"""

import os
import sys
from flask import Flask
from models import db, PDU, PDUPort, OutletGroup, init_db

def reset_database():
    """Reset the database and recreate with 36 outlets and new features"""
    try:
        # Remove existing database file
        db_file = 'pdu_monitor.db'
        if os.path.exists(db_file):
            os.remove(db_file)
            print(f"Removed existing database: {db_file}")
        
        # Create Flask app for database operations
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pdu_monitor.db'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Initialize database
        db.init_app(app)
        
        with app.app_context():
            # Create all tables
            db.create_all()
            print("Created all database tables")
            
            # Initialize with default data
            init_db()
            print("Database initialization completed")
            
            # Verify the setup
            pdu = PDU.query.first()
            if pdu:
                outlets = PDUPort.query.filter_by(pdu_id=pdu.id).all()
                print(f"✅ Database reset successful!")
                print(f"   PDU: {pdu.name} ({pdu.ip_address})")
                print(f"   Outlets: {len(outlets)} outlets created")
                print(f"   Outlet range: {outlets[0].port_number} to {outlets[-1].port_number}")
                print(f"   New features: Outlet grouping, custom selection, password protection")
            else:
                print("❌ Error: No PDU found after reset")
                
    except Exception as e:
        print(f"❌ Error resetting database: {str(e)}")
        return False
    
    return True

if __name__ == '__main__':
    print("🔄 Raritan PX3-5892 Outlet Monitor Database Reset Tool")
    print("This will delete the existing database and recreate it with 36 outlets.")
    print("New features include outlet grouping, custom selection, and password protection.")
    print()
    
    response = input("Are you sure you want to continue? (y/N): ")
    if response.lower() in ['y', 'yes']:
        if reset_database():
            print("\n✅ Database reset completed successfully!")
            print("New PDU IP: 172.0.250.9")
            print("Group management password: admin123")
            print("You can now start the system with: ./start.sh")
        else:
            print("\n❌ Database reset failed!")
            sys.exit(1)
    else:
        print("Database reset cancelled.")
