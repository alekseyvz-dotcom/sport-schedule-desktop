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
    conn.autocommit = False

    # ВАЖНО: пул должен раздавать "чистое" соединение.
    # Если кто-то оставил транзакцию открытой или в ошибке — очищаем здесь.
    try:
        if conn.status != extensions.STATUS_READY:
            conn.rollback()

        # Рекомендуется при TIMESTAMPTZ, если вы передаёте naive datetime из UI.
        # Поставьте вашу локальную TZ (или уберите, если везде используете aware datetime/UTC).
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Europe/Moscow';")
    except Exception:
        # соединение "битое" — закрываем и возвращаем в пул как закрытое
        try:
            conn.close()
        finally:
            _db_pool.putconn(conn, close=True)
        raise

    return conn


def put_conn(conn):
    if _db_pool is None or conn is None:
        return

    try:
        # Критично: перед возвратом в пул не должны оставаться открытые транзакции.
        # Если кто-то забыл commit/rollback — откатываем.
        if conn.status != extensions.STATUS_READY:
            conn.rollback()
    except Exception:
        try:
            conn.close()
        finally:
            _db_pool.putconn(conn, close=True)
        return

    _db_pool.putconn(conn)
