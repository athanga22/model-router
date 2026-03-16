#!/usr/bin/env python3
"""Verify database connection and schema."""
import sys
sys.path.append(".")
from app.database import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'requests'
    ORDER BY ordinal_position;
""")
rows = cur.fetchall()

print("requests table columns:")
for row in rows:
    print(f"  {row[0]:<20} {row[1]}")

cur.close()
conn.close()