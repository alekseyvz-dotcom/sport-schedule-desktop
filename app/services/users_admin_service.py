# app/services/users_admin_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.auth import hash_password_pbkdf2
from app.db import get_conn, put_conn


@dataclass(frozen=True)
class AdminUserRow:
    id: int
    username: str
    full_name: str
    role_code: str
    is_active: bool


@dataclass(frozen=True)
class OrgPermRow:
    org_id: int
    org_name: str
    org_is_active: bool
    can_view: bool
    can_edit: bool

@dataclass(frozen=True)
class RoleRow:
    code: str
    name: str

def list_users() -> List[AdminUserRow]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, username, COALESCE(full_name,'') AS full_name, role_code, is_active
                FROM public.app_users
                ORDER BY username
            """)
            rows = cur.fetchall()
            conn.commit()
            return [
                AdminUserRow(
                    id=int(r["id"]),
                    username=str(r["username"]),
                    full_name=str(r["full_name"] or ""),
                    role_code=str(r["role_code"]),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_user(username: str, password: str, full_name: str, role_code: str, is_active: bool = True) -> int:
    username = (username or "").strip()
    if not username:
        raise ValueError("Пустой логин")
    if not password:
        raise ValueError("Пустой пароль")

    pw_hash = hash_password_pbkdf2(password)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO public.app_users(username, password_hash, full_name, role_code, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (username, pw_hash, (full_name or ""), role_code, bool(is_active)))
            user_id = int(cur.fetchone()["id"])
            conn.commit()
            return user_id
    finally:
        if conn:
            put_conn(conn)


def update_user(user_id: int, full_name: str, role_code: str, is_active: bool) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.app_users
                SET full_name = %s, role_code = %s, is_active = %s
                WHERE id = %s
            """, ((full_name or ""), role_code, bool(is_active), int(user_id)))
            conn.commit()
    finally:
        if conn:
            put_conn(conn)


def set_password(user_id: int, new_password: str) -> None:
    if not new_password:
        raise ValueError("Пустой пароль")
    pw_hash = hash_password_pbkdf2(new_password)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE public.app_users
                SET password_hash = %s
                WHERE id = %s
            """, (pw_hash, int(user_id)))
            conn.commit()
    finally:
        if conn:
            put_conn(conn)


def list_roles() -> List[RoleRow]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT code, name FROM public.roles ORDER BY name, code")
            rows = cur.fetchall()
            conn.commit()
            return [RoleRow(code=str(r["code"]), name=str(r["name"])) for r in rows]
    finally:
        if conn:
            put_conn(conn)
            
def list_org_permissions(user_id: int) -> List[OrgPermRow]:
    """
    Всегда возвращаем ВСЕ учреждения (активные и неактивные) + права.
    UI сам решает, показывать неактивные или нет.
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    o.id AS org_id,
                    o.name AS org_name,
                    o.is_active AS org_is_active,
                    COALESCE(p.can_view, false) AS can_view,
                    COALESCE(p.can_edit, false) AS can_edit
                FROM public.sport_orgs o
                LEFT JOIN public.app_user_org_permissions p
                       ON p.org_id = o.id AND p.user_id = %s
                ORDER BY o.is_active DESC, o.name
            """, (int(user_id),))
            rows = cur.fetchall()
            conn.commit()
            return [
                OrgPermRow(
                    org_id=int(r["org_id"]),
                    org_name=str(r["org_name"]),
                    org_is_active=bool(r["org_is_active"]),
                    can_view=bool(r["can_view"]),
                    can_edit=bool(r["can_edit"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)

def save_org_permissions(user_id: int, perms: List[OrgPermRow]) -> None:
    """
    Полная перезапись прав пользователя на учреждения.
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.app_user_org_permissions WHERE user_id = %s", (int(user_id),))

            for p in perms:
                if not p.can_view and not p.can_edit:
                    continue
                cur.execute("""
                    INSERT INTO public.app_user_org_permissions(user_id, org_id, can_view, can_edit)
                    VALUES (%s, %s, %s, %s)
                """, (int(user_id), int(p.org_id), bool(p.can_view), bool(p.can_edit)))

            conn.commit()
    finally:
        if conn:
            put_conn(conn)
