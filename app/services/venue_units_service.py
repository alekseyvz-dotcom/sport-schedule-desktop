from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class VenueUnit:
    id: int
    venue_id: int
    code: str
    name: str
    sort_order: int
    is_active: bool


def list_venue_units(venue_id: int, include_inactive: bool = False) -> List[VenueUnit]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT id, venue_id, code, name, sort_order, is_active
                FROM public.venue_units
                WHERE venue_id = %(venue_id)s
            """
            params = {"venue_id": int(venue_id)}
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY sort_order, name"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                VenueUnit(
                    id=int(r["id"]),
                    venue_id=int(r["venue_id"]),
                    code=str(r["code"]),
                    name=str(r["name"]),
                    sort_order=int(r["sort_order"]),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)
