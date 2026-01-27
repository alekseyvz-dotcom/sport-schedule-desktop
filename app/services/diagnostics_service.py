from psycopg2.extras import RealDictCursor
from app.db import get_conn, put_conn
from app.settings_manager import get_database_url

def connection_report() -> str:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("select current_database() as db, current_user as usr;")
            a = cur.fetchone()
            cur.execute("select inet_server_addr()::text as host, inet_server_port() as port;")
            b = cur.fetchone()
            cur.execute("select current_schema() as schema;")
            c = cur.fetchone()

        return (
            "DATABASE_URL(from settings.dat):\n"
            f"{get_database_url()}\n\n"
            "Connected to:\n"
            f"db={a['db']}, user={a['usr']}, host={b['host']}:{b['port']}, schema={c['schema']}"
        )
    finally:
        if conn:
            put_conn(conn)
