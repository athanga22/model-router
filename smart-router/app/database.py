"""Database connection and helpers."""

import os
import glob
import sys
import psycopg
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

_pool: ConnectionPool | None = None


def _build_conninfo() -> str:
    """Build a psycopg connection string from env vars."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("POSTGRES_HOST", "")
    user = os.getenv("POSTGRES_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    dbname = os.getenv("POSTGRES_DB", "")

    # Unix socket (e.g. Cloud SQL): host is socket path
    if host.startswith("/"):
        return f"host={host} dbname={dbname} user={user} password={password}"

    if host:
        return f"host={host} port=5432 dbname={dbname} user={user} password={password}"
    return f"dbname={dbname} user={user} password={password}"


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_build_conninfo(),
            min_size=1,
            max_size=10,
        )
    return _pool


def get_connection():
    """Return a pooled connection context manager. Use with `with get_connection() as conn:`"""
    return get_pool().connection()


def run_migrations():
    """One-time migration runner — uses a direct connection, not the pool."""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    migrations_dir = os.path.join(_root, "migrations")

    conn = psycopg.connect(_build_conninfo())
    cur = conn.cursor()
    try:
        for path in sorted(glob.glob(os.path.join(migrations_dir, "*.sql"))):
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            try:
                cur.execute(sql)
                conn.commit()
                print(f"OK  {os.path.relpath(path, _root)}")
            except Exception as e:
                print(f"FAILED  {os.path.relpath(path, _root)}: {e}", file=sys.stderr)
                conn.rollback()
                sys.exit(1)
        print("Migrations complete.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run_migrations()
