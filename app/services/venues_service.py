from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class Venue:
    id: int
    org_id: int
    name: str
    sport_type: Optional[str]
    capacity: Optional[int]
    comment: Optional[str]
    is_active: bool


def list_venues(org_id: int, include_inactive: bool = False) -> List[Venue]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT v.id, v.org_id, v.name, v.sport_type, v.capacity, v.comment, v.is_active
                FROM public.venues v
                WHERE v.org_id = %s
            """
            params = [int(org_id)]
            if not include_inactive:
                sql += " AND v.is_active = true"
            sql += " ORDER BY v.name"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                Venue(
                    id=int(r["id"]),
                    org_id=int(r["org_id"]),
                    name=str(r["name"]),
                    sport_type=r.get("sport_type"),
                    capacity=r.get("capacity"),
                    comment=r.get("comment"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_venue(
    org_id: int,
    name: str,
    sport_type: str = "",
    capacity: Optional[int] = None,
    comment: str = "",
) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название площадки не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.venues(org_id, name, sport_type, capacity, comment, is_active)
                    VALUES (%s, %s, %s, %s, %s, true)
                    RETURNING id
                    """,
                    (int(org_id), name, sport_type or None, capacity, comment or None),
                )
                return int(cur.fetchone()[0])
    finally:
        if conn:
            put_conn(conn)


def update_venue(
    venue_id: int,
    name: str,
    sport_type: str = "",
    capacity: Optional[int] = None,
    comment: str = "",
):
    name = (name or "").strip()
    if not name:
        raise ValueError("Название площадки не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.venues
                    SET name=%s, sport_type=%s, capacity=%s, comment=%s
                    WHERE id=%s
                    """,
                    (name, sport_type or None, capacity, comment or None, int(venue_id)),
                )
    finally:
        if conn:
            put_conn(conn)


def set_venue_active(venue_id: int, is_active: bool):
    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.venues SET is_active=%s WHERE id=%s",
                    (bool(is_active), int(venue_id)),
                )
    finally:
        if conn:
            put_conn(conn)
