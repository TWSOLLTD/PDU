#!/usr/bin/env python3
"""
Script to fix the database by creating the missing system_settings table
"""

import sqlite3
import os

def fix_database():
    """Create the missing system_settings table"""
    
    db_path = 'pdu_monitor.db'
    
    if not os.path.exists(db_path):
        print(f"Database file {db_path} not found!")
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if system_settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_settings'")
        table_exists = cursor.fetchone()
        
        if table_exists:
            print("system_settings table already exists!")
            return True
        
        # Create the system_settings table
        print("Creating system_settings table...")
        cursor.execute("""
            CREATE TABLE system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Commit the changes
        conn.commit()
        
        # Verify the table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_settings'")
        if cursor.fetchone():
            print("✅ system_settings table created successfully!")
            
            # Show all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"Current tables: {[table[0] for table in tables]}")
            
            return True
        else:
            print("❌ Failed to create system_settings table!")
            return False
            
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("Fixing database...")
    success = fix_database()
    if success:
        print("Database fix completed successfully!")
    else:
        print("Database fix failed!")
