"""Database connection and helpers."""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def run_migrations():
    conn = get_connection()
    cur = conn.cursor()
    with open("migrations/001_create_requests_table.sql", "r") as f:
        cur.execute(f.read())
    conn.commit()
    cur.close()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    run_migrations()