from __future__ import annotations

from dataclasses import dataclass
from datetime import time
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
    work_start: time
    work_end: time
    is_24h: bool


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
                SELECT
                    o.id,
                    o.name,
                    o.address,
                    o.comment,
                    o.is_active,
                    o.work_start,
                    o.work_end,
                    o.is_24h
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
                    work_start=r["work_start"],
                    work_end=r["work_end"],
                    is_24h=bool(r.get("is_24h") or False),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def _validate_work_time(*, is_24h: bool, work_start: time, work_end: time) -> None:
    if is_24h:
        return
    if work_end <= work_start:
        raise ValueError("Окончание рабочего дня должно быть позже начала (смены через полночь не поддерживаются).")


def create_org(
    name: str,
    address: str = "",
    comment: str = "",
    *,
    work_start: time = time(8, 0),
    work_end: time = time(22, 0),
    is_24h: bool = False,
) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название учреждения не может быть пустым")

    _validate_work_time(is_24h=bool(is_24h), work_start=work_start, work_end=work_end)

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.sport_orgs(
                        name, address, comment, is_active, work_start, work_end, is_24h
                    )
                    VALUES (%s, %s, %s, true, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        name,
                        address or None,
                        comment or None,
                        work_start,
                        work_end,
                        bool(is_24h),
                    ),
                )
                return int(cur.fetchone()[0])
    finally:
        if conn:
            put_conn(conn)


def update_org(
    org_id: int,
    name: str,
    address: str = "",
    comment: str = "",
    *,
    work_start: time,
    work_end: time,
    is_24h: bool = False,
) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название учреждения не может быть пустым")

    _validate_work_time(is_24h=bool(is_24h), work_start=work_start, work_end=work_end)

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.sport_orgs
                    SET
                        name=%s,
                        address=%s,
                        comment=%s,
                        work_start=%s,
                        work_end=%s,
                        is_24h=%s
                    WHERE id=%s
                    """,
                    (
                        name,
                        address or None,
                        comment or None,
                        work_start,
                        work_end,
                        bool(is_24h),
                        int(org_id),
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError("Учреждение не найдено")
    finally:
        if conn:
            put_conn(conn)


def set_org_active(org_id: int, is_active: bool) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.sport_orgs SET is_active=%s WHERE id=%s",
                    (bool(is_active), int(org_id)),
                )
                if cur.rowcount != 1:
                    raise ValueError("Учреждение не найдено")
    finally:
        if conn:
            put_conn(conn)
