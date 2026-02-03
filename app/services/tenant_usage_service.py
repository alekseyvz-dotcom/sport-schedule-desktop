from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

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
    if end_dt <= start_dt:
        raise ValueError("end_dt <= start_dt")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
                ),
                b2 AS (
                    SELECT
                        -- виртуальный "tenant" для аналитики:
                        --  - GZ без tenant_id => отдельная строка "Гос. задание"
                        CASE
                            WHEN b1.tenant_id IS NULL AND b1.activity = 'GZ' THEN 'GZ'
                            WHEN b1.tenant_id IS NULL THEN 'NONE'
                            ELSE 'T:' || b1.tenant_id::text
                        END AS tenant_key,

                        b1.tenant_id,
                        b1.activity,
                        b1.status,
                        b1.sec
                    FROM b1
                )
                SELECT
                    b2.tenant_key,

                    -- tenant_id оставляем NULL (это "виртуальные" строки)
                    CASE WHEN b2.tenant_key LIKE 'T:%' THEN b2.tenant_id ELSE NULL END AS tenant_id,

                    CASE
                        WHEN b2.tenant_key = 'GZ' THEN 'Гос. задание'
                        WHEN b2.tenant_key = 'NONE' THEN 'Без арендатора'
                        ELSE COALESCE(t.name, 'Без арендатора')
                    END AS tenant_name,

                    CASE
                        WHEN b2.tenant_key IN ('GZ', 'NONE') THEN 'unknown'
                        ELSE COALESCE(t.tenant_kind, 'unknown')
                    END AS tenant_kind,

                    CASE
                        WHEN b2.tenant_key IN ('GZ', 'NONE') THEN 'unknown'
                        ELSE COALESCE(t.rent_kind, 'unknown')
                    END AS rent_kind,

                    COALESCE(SUM(CASE WHEN b2.activity = 'PD' THEN b2.sec ELSE 0 END), 0)::bigint AS pd_sec,
                    COALESCE(SUM(CASE WHEN b2.activity = 'GZ' THEN b2.sec ELSE 0 END), 0)::bigint AS gz_sec,
                    COALESCE(SUM(b2.sec), 0)::bigint AS total_sec,

                    COUNT(*)::int AS bookings_count,
                    COALESCE(SUM(CASE WHEN b2.status = 'cancelled' THEN 1 ELSE 0 END), 0)::int AS cancelled_count
                FROM b2
                LEFT JOIN public.tenants t
                       ON (b2.tenant_key LIKE 'T:%' AND t.id = b2.tenant_id)
            """

            if only_active_tenants:
                # показываем "виртуальные" строки всегда, а реальных — только активных
                sql += " WHERE (b2.tenant_key IN ('GZ','NONE') OR t.is_active = true)"

            sql += """
                GROUP BY
                    b2.tenant_key,
                    CASE WHEN b2.tenant_key LIKE 'T:%' THEN b2.tenant_id ELSE NULL END,
                    tenant_name,
                    tenant_kind,
                    rent_kind
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

