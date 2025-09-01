-- SQL script to add SystemSettings table to the database
-- Run this with: sqlite3 pdu_monitor.db < fix_database.sql

-- Check if SystemSettings table exists
SELECT CASE 
    WHEN EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='system_settings') 
    THEN 'SystemSettings table already exists'
    ELSE 'Creating SystemSettings table...'
END;

-- Create SystemSettings table if it doesn't exist
CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Show all tables
SELECT 'Current tables:' as info;
SELECT name FROM sqlite_master WHERE type='table';

-- Show SystemSettings table structure
SELECT 'SystemSettings table structure:' as info;
PRAGMA table_info(system_settings);
