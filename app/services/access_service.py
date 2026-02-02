# app/services/access_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class OrgAccess:
    org_id: int
    can_view: bool
    can_edit: bool


def list_allowed_org_ids(user_id: int, role_code: str) -> List[int]:
    """
    Возвращает список org_id, которые пользователь может видеть (can_view=true).
    admin -> все активные учреждения.
    """
    role = (role_code or "").lower()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if role == "admin":
                cur.execute(
                    """
                    SELECT id
                    FROM public.sport_orgs
                    WHERE is_active = true
                    ORDER BY name
                    """
                )
                return [int(r["id"]) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT org_id
                FROM public.app_user_org_permissions
                WHERE user_id = %s AND can_view = true
                """,
                (int(user_id),),
            )
            return [int(r["org_id"]) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)


def get_org_access(user_id: int, role_code: str, org_id: int) -> OrgAccess:
    """
    Возвращает can_view/can_edit для конкретного учреждения.
    admin -> (true,true)
    """
    role = (role_code or "").lower()
    if role == "admin":
        return OrgAccess(org_id=int(org_id), can_view=True, can_edit=True)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT can_view, can_edit
                FROM public.app_user_org_permissions
                WHERE user_id = %s AND org_id = %s
                """,
                (int(user_id), int(org_id)),
            )
            r = cur.fetchone()
            if not r:
                return OrgAccess(org_id=int(org_id), can_view=False, can_edit=False)
            return OrgAccess(org_id=int(org_id), can_view=bool(r["can_view"]), can_edit=bool(r["can_edit"]))
    finally:
        if conn:
            put_conn(conn)
