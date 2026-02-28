"""Database connection and helpers."""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    host = os.getenv("POSTGRES_HOST")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("DB_PASSWORD")
    dbname = os.getenv("POSTGRES_DB")

    # psycopg2 Unix socket: pass host as unix_socket_directory
    if host and host.startswith("/"):
        return psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=5432
        )

    return psycopg2.connect(
        host=host,
        user=user,
        password=password,
        dbname=dbname
    )

def run_migrations():
    import glob
    import sys
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