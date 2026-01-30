from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class TenantUsageRow:
    tenant_id: Optional[int]          # может быть NULL в bookings
    tenant_name: str                  # "Без арендатора" если NULL
    tenant_kind: str                  # legal/person/unknown
    rent_kind: str                    # long_term/one_time/unknown

    pd_sec: int
    gz_sec: int
    total_sec: int

    bookings_count: int
    cancelled_count: int


def list_usage_by_tenants(
    *,
    start_dt: datetime,
    end_dt: datetime,
    org_id: Optional[int] = None,
    include_cancelled: bool = False,
    only_active_tenants: bool = False,
) -> List[TenantUsageRow]:
    """
    Агрегация по арендаторам за период [start_dt, end_dt).
    Считает пересечение брони с периодом.
    """
    if end_dt <= start_dt:
        raise ValueError("end_dt <= start_dt")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # ВАЖНО:
            # seconds считаем по пересечению: [max(starts_at,start_dt), min(ends_at,end_dt)]
            # и только если пересечение положительное.
            sql = """
                WITH b0 AS (
                    SELECT
                        b.tenant_id,
                        b.activity,
                        b.status,
                        GREATEST(b.starts_at, %(start_dt)s) AS s,
                        LEAST(b.ends_at, %(end_dt)s) AS e
                    FROM public.bookings b
                    JOIN public.venues v ON v.id = b.venue_id
                    WHERE b.starts_at < %(end_dt)s
                      AND b.ends_at > %(start_dt)s
            """
            params: Dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}

            if org_id is not None:
                sql += " AND v.org_id = %(org_id)s"
                params["org_id"] = int(org_id)

            if not include_cancelled:
                sql += " AND b.status <> 'cancelled'"

            sql += """
                ),
                b1 AS (
                    SELECT
                        tenant_id,
                        activity,
                        status,
                        EXTRACT(EPOCH FROM (e - s))::bigint AS sec
                    FROM b0
                    WHERE e > s
                )
                SELECT
                    t.id AS tenant_id,
                    COALESCE(t.name, 'Без арендатора') AS tenant_name,
                    COALESCE(t.tenant_kind, 'unknown') AS tenant_kind,
                    COALESCE(t.rent_kind, 'unknown') AS rent_kind,

                    COALESCE(SUM(CASE WHEN b1.activity = 'PD' THEN b1.sec ELSE 0 END), 0)::bigint AS pd_sec,
                    COALESCE(SUM(CASE WHEN b1.activity = 'GZ' THEN b1.sec ELSE 0 END), 0)::bigint AS gz_sec,
                    COALESCE(SUM(b1.sec), 0)::bigint AS total_sec,

                    COUNT(*)::int AS bookings_count,
                    COALESCE(SUM(CASE WHEN b1.status = 'cancelled' THEN 1 ELSE 0 END), 0)::int AS cancelled_count
                FROM b1
                LEFT JOIN public.tenants t ON t.id = b1.tenant_id
            """

            if only_active_tenants:
                # NULL tenant_id тоже отфильтруем (если нужно оставить "Без арендатора" — скажи)
                sql += " WHERE t.is_active = true"

            sql += """
                GROUP BY t.id, t.name, t.tenant_kind, t.rent_kind
                ORDER BY total_sec DESC, tenant_name
            """

            cur.execute(sql, params)
            rows = cur.fetchall()

            out: List[TenantUsageRow] = []
            for r in rows:
                out.append(
                    TenantUsageRow(
                        tenant_id=(int(r["tenant_id"]) if r["tenant_id"] is not None else None),
                        tenant_name=str(r["tenant_name"] or ""),
                        tenant_kind=str(r["tenant_kind"] or "unknown"),
                        rent_kind=str(r["rent_kind"] or "unknown"),
                        pd_sec=int(r["pd_sec"] or 0),
                        gz_sec=int(r["gz_sec"] or 0),
                        total_sec=int(r["total_sec"] or 0),
                        bookings_count=int(r["bookings_count"] or 0),
                        cancelled_count=int(r["cancelled_count"] or 0),
                    )
                )
            return out
    finally:
        if conn:
            put_conn(conn)
