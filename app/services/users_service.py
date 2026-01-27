from dataclasses import dataclass
from typing import Set, Optional, Tuple

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.auth import verify_password

@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    full_name: str
    role_code: str
    permissions: Set[str]

def authenticate(username: str, password: str) -> Optional[AuthUser]:
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return None

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, username, password_hash, full_name, role_code, is_active
                FROM public.app_users
                WHERE username = %s
                """,
                (username,),
            )
            u = cur.fetchone()
            if not u or not u.get("is_active"):
                return None

            if not verify_password(password, u["password_hash"]):
                return None

            cur.execute(
                """
                SELECT perm_code
                FROM public.app_user_permissions
                WHERE user_id = %s
                """,
                (u["id"],),
            )
            perms = {r["perm_code"] for r in cur.fetchall()}

            return AuthUser(
                id=int(u["id"]),
                username=str(u["username"]),
                full_name=str(u.get("full_name") or ""),
                role_code=str(u["role_code"]),
                permissions=perms,
            )
    finally:
        if conn:
            put_conn(conn)
