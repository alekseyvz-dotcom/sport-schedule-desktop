from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn

@dataclass(frozen=True)
class Tenant:
    id: int
    name: str
    inn: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    comment: Optional[str]
    is_active: bool

def list_tenants(search: str = "", include_inactive: bool = False) -> List[Tenant]:
    search = (search or "").strip()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params = {}

            if not include_inactive:
                where.append("t.is_active = true")

            if search:
                where.append(
                    "(t.name ILIKE %(q)s OR t.inn ILIKE %(q)s OR t.phone ILIKE %(q)s)"
                )
                params["q"] = f"%{search}%"

            sql = """
                SELECT t.id, t.name, t.inn, t.phone, t.email, t.comment, t.is_active
                FROM public.tenants t
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY t.name"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                Tenant(
                    id=int(r["id"]),
                    name=str(r["name"]),
                    inn=r.get("inn"),
                    phone=r.get("phone"),
                    email=r.get("email"),
                    comment=r.get("comment"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)

def create_tenant(name: str, inn: str = "", phone: str = "", email: str = "", comment: str = "") -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название арендатора не может быть пустым")

    conn = None
    try:
        conn = get_conn()

        # DEBUG: проверим, не read-only ли транзакция
        with conn.cursor() as cur:
            cur.execute("show transaction_read_only;")
            ro = cur.fetchone()[0]
            if ro == "on":
                raise RuntimeError("DB session is read-only (transaction_read_only=on)")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.tenants(name, inn, phone, email, comment, is_active)
                VALUES (%s, %s, %s, %s, %s, true)
                RETURNING id
                """,
                (name, inn or None, phone or None, email or None, comment or None),
            )
            new_id = int(cur.fetchone()[0])

        conn.commit()   # ЯВНО

        return new_id

    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)

def update_tenant(tenant_id: int, name: str, inn: str = "", phone: str = "", email: str = "", comment: str = ""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название арендатора не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.tenants
                    SET name=%s, inn=%s, phone=%s, email=%s, comment=%s
                    WHERE id=%s
                    """,
                    (name, inn or None, phone or None, email or None, comment or None, int(tenant_id)),
                )
    finally:
        if conn:
            put_conn(conn)

def set_tenant_active(tenant_id: int, is_active: bool):
    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.tenants SET is_active=%s WHERE id=%s",
                    (bool(is_active), int(tenant_id)),
                )
    finally:
        if conn:
            put_conn(conn)
