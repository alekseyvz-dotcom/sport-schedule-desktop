from __future__ import annotations

from functools import lru_cache
from typing import Generator

from fastapi import Request, HTTPException
from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


def get_db() -> Generator:
    conn = get_conn()
    try:
        yield conn
    finally:
        put_conn(conn)


def get_current_user(request: Request) -> dict:
    """Читает user из session. Если нет — редирект на логин."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


def require_org_access(user: dict, org_id: int, conn) -> dict:
    """Проверяет доступ пользователя к учреждению."""
    role = user.get("role_code", "")
    user_id = user["id"]

    if role == "admin":
        return {"can_view": True, "can_edit": True}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT can_view, can_edit
            FROM app_user_org_permissions
            WHERE user_id = %s AND org_id = %s
            """,
            (user_id, org_id),
        )
        row = cur.fetchone()

    if not row or not row["can_view"]:
        raise HTTPException(403, "Нет доступа к этому учреждению")

    return row
