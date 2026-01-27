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

    # autocommit выключаем — ок
    conn.autocommit = False

    # ВАЖНО: если соединение вернулось "грязным" (кто-то не закрыл транзакцию),
    # чистим его здесь, чтобы не тащить мусор дальше.
    try:
        if conn.status == extensions.STATUS_IN_ERROR:
            conn.rollback()
        # если транзакция была открыта и не завершена — тоже откатим
        elif conn.status != extensions.STATUS_READY:
            conn.rollback()
    except Exception:
        # если соединение битое — закроем и отдадим пулу как закрытое
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
        # Откатываем ТОЛЬКО если есть ошибка.
        # Если транзакция просто открыта (BEGIN), это не ошибка — но чтобы пул
        # всегда раздавал чистое соединение, можно откатить и её.
        if conn.status == extensions.STATUS_IN_ERROR:
            conn.rollback()
        elif conn.status != extensions.STATUS_READY:
            # чтобы соединения в пуле всегда были чистыми:
            conn.rollback()
    except Exception:
        try:
            conn.close()
        finally:
            _db_pool.putconn(conn, close=True)
        return

    _db_pool.putconn(conn)
