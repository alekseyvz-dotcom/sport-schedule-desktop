from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import RealDictCursor
from app.db import get_conn, put_conn


@dataclass(frozen=True)
class RefOrg:
    id: int
    name: str


@dataclass(frozen=True)
class RefVenue:
    id: int
    org_id: int
    name: str


@dataclass(frozen=True)
class RefTenant:
    id: int
    name: str


def list_active_orgs() -> List[RefOrg]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name
                FROM public.sport_orgs
                WHERE is_active = true
                ORDER BY name
                """
            )
            return [RefOrg(int(r["id"]), str(r["name"])) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)


def list_active_venues(org_id: int) -> List[RefVenue]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, org_id, name
                FROM public.venues
                WHERE org_id = %s AND is_active = true
                ORDER BY name
                """,
                (int(org_id),),
            )
            return [RefVenue(int(r["id"]), int(r["org_id"]), str(r["name"])) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)


def list_active_tenants() -> List[RefTenant]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name
                FROM public.tenants
                WHERE is_active = true
                ORDER BY name
                """
            )
            return [RefTenant(int(r["id"]), str(r["name"])) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)
