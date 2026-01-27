import psycopg2
from psycopg2 import pool, extensions
from app.settings_manager import get_database_url

_db_pool: pool.SimpleConnectionPool | None = None


def init_pool(minconn: int = 1, maxconn: int = 5):
    global _db_pool
    dsn = get_database_url()
    _db_pool = psycopg2.pool.SimpleConnectionPool(minconn, maxconn, dsn)


def get_conn():
    if _db_pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool().")
    conn = _db_pool.getconn()
    # на всякий случай приводим в нормальное состояние
    conn.autocommit = False
    return conn


def put_conn(conn):
    if _db_pool is None or conn is None:
        return

    try:
        # Если соединение осталось в незавершенной/ошибочной транзакции — откатываем.
        # Это важно при использовании пула.
        if conn.status != extensions.STATUS_READY:
            conn.rollback()
    except Exception:
        # если соединение "битое" — закрываем, чтобы пул не раздавал его снова
        try:
            conn.close()
        finally:
            _db_pool.putconn(conn, close=True)
        return

    _db_pool.putconn(conn)
