# app/services/access_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.db_conn import db_conn


@dataclass(frozen=True)
class OrgAccess:
    org_id: int
    can_view: bool
    can_edit: bool


def list_allowed_orgs_for_user(user_id: int, role_code: str) -> list[int]:
    # админ видит всё
    if (role_code or "").lower() == "admin":
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id
                FROM public.sport_orgs
                WHERE is_active = true
                ORDER BY name
            """)
            return [int(r[0]) for r in cur.fetchall()]

    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT org_id
            FROM public.app_user_org_permissions
            WHERE user_id = %s AND can_view = true
        """, (user_id,))
        return [int(r[0]) for r in cur.fetchall()]


def get_org_access(user_id: int, role_code: str, org_id: int) -> OrgAccess:
    if (role_code or "").lower() == "admin":
        return OrgAccess(org_id=org_id, can_view=True, can_edit=True)

    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT can_view, can_edit
            FROM public.app_user_org_permissions
            WHERE user_id = %s AND org_id = %s
        """, (user_id, org_id))
        row = cur.fetchone()

    if not row:
        return OrgAccess(org_id=org_id, can_view=False, can_edit=False)

    return OrgAccess(org_id=org_id, can_view=bool(row[0]), can_edit=bool(row[1]))
