from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class SportOrg:
    id: int
    name: str
    address: Optional[str]
    comment: Optional[str]
    is_active: bool


def list_orgs(search: str = "", include_inactive: bool = False) -> List[SportOrg]:
    search = (search or "").strip()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params = {}
            if not include_inactive:
                where.append("o.is_active = true")
            if search:
                where.append("(o.name ILIKE %(q)s OR o.address ILIKE %(q)s)")
                params["q"] = f"%{search}%"

            sql = """
                SELECT o.id, o.name, o.address, o.comment, o.is_active
                FROM public.sport_orgs o
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY o.name"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                SportOrg(
                    id=int(r["id"]),
                    name=str(r["name"]),
                    address=r.get("address"),
                    comment=r.get("comment"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_org(name: str, address: str = "", comment: str = "") -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название учреждения не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.sport_orgs(name, address, comment, is_active)
                    VALUES (%s, %s, %s, true)
                    RETURNING id
                    """,
                    (name, address or None, comment or None),
                )
                return int(cur.fetchone()[0])
    finally:
        if conn:
            put_conn(conn)


def update_org(org_id: int, name: str, address: str = "", comment: str = ""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название учреждения не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.sport_orgs
                    SET name=%s, address=%s, comment=%s
                    WHERE id=%s
                    """,
                    (name, address or None, comment or None, int(org_id)),
                )
    finally:
        if conn:
            put_conn(conn)


def set_org_active(org_id: int, is_active: bool):
    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.sport_orgs SET is_active=%s WHERE id=%s",
                    (bool(is_active), int(org_id)),
                )
    finally:
        if conn:
            put_conn(conn)
