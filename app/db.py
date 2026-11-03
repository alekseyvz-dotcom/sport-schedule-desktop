import psycopg2
from psycopg2 import pool, extensions

from app.settings_manager import get_database_url

_db_pool: pool.SimpleConnectionPool | None = None


def init_pool(minconn: int = 1, maxconn: int = 5):
    """Test-branch guard: fail closed before and after opening the pool."""
    global _db_pool
    dsn = get_database_url()
    try:
        params = extensions.parse_dsn(dsn)
    except Exception:
        raise RuntimeError("Тестовый запуск остановлен: неверные настройки подключения.") from None

    allowed = {"host", "port", "dbname", "user", "password", "sslmode", "connect_timeout"}
    if (set(params) - allowed or params.get("host") != "185.55.58.31"
            or params.get("port", "5432") != "5432"
            or params.get("dbname") != "sport_schedule_test"
            or params.get("user") != "sport_test_user"):
        raise RuntimeError("Тестовый запуск остановлен: настройки должны указывать на тестовую базу и тестового пользователя.")

    test_pool = psycopg2.pool.SimpleConnectionPool(minconn, maxconn, dsn)
    try:
        conn = test_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), session_user, current_user")
                db_name, session_name, effective_user = cur.fetchone()
            if (db_name, session_name, effective_user) != (
                    "sport_schedule_test", "sport_test_user", "sport_test_user"):
                raise RuntimeError("Тестовый запуск остановлен: сервер подтвердил неверную базу или пользователя.")
        finally:
            test_pool.putconn(conn)
    except Exception:
        test_pool.closeall()
        raise
    _db_pool = test_pool


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
