#!/usr/bin/env python3
"""
Database migration script to add status column to port_power_readings table
"""

import sqlite3
import os
from datetime import datetime

def migrate_database():
    """Add status column to port_power_readings table"""
    
    # Database file path
    db_path = 'pdu_monitor.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if status column already exists
        cursor.execute("PRAGMA table_info(port_power_readings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'status' in columns:
            print("Status column already exists in port_power_readings table")
            conn.close()
            return True
        
        # Add status column
        print("Adding status column to port_power_readings table...")
        cursor.execute("ALTER TABLE port_power_readings ADD COLUMN status VARCHAR(10)")
        
        # Commit changes
        conn.commit()
        print("✅ Status column added successfully!")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(port_power_readings)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'status' in columns:
            print("✅ Verification: Status column is now present")
        else:
            print("❌ Verification failed: Status column not found")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        return False

if __name__ == '__main__':
    print("🔄 Starting database migration...")
    print(f"Timestamp: {datetime.now()}")
    print("-" * 50)
    
    success = migrate_database()
    
    print("-" * 50)
    if success:
        print("🎉 Migration completed successfully!")
        print("The status column has been added to port_power_readings table.")
        print("You can now restart the application to use the new status functionality.")
    else:
        print("💥 Migration failed!")
        print("Please check the error messages above and try again.")
