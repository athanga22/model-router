"""Database connection and helpers."""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def run_migrations():
    import glob
    import sys
    # Resolve migrations dir relative to this file so it works from any cwd
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migrations_dir = os.path.join(_root, "migrations")
    conn = get_connection()
    cur = conn.cursor()
    try:
        for path in sorted(glob.glob(os.path.join(migrations_dir, "*.sql"))):
            with open(path, "r") as f:
                sql = f.read()
            try:
                cur.execute(sql)
                conn.commit()
                print(f"OK  {os.path.relpath(path, _root)}")
            except Exception as e:
                print(f"FAILED  {os.path.relpath(path, _root)}: {e}", file=sys.stderr)
                conn.rollback()
                cur.close()
                conn.close()
                sys.exit(1)
        print("Migrations complete.")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_migrations()