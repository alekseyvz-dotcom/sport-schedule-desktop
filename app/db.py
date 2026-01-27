import psycopg2
from psycopg2 import pool
from app.settings_manager import get_database_url

_db_pool: pool.SimpleConnectionPool | None = None

def init_pool(minconn: int = 1, maxconn: int = 5):
    global _db_pool
    dsn = get_database_url()
    _db_pool = psycopg2.pool.SimpleConnectionPool(minconn, maxconn, dsn)

def get_conn():
    if _db_pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool().")
    return _db_pool.getconn()

def put_conn(conn):
    if _db_pool is not None and conn is not None:
        _db_pool.putconn(conn)
