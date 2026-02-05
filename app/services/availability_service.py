# app/services/availability_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import List, Optional, Dict, Any

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class SlotConflict:
    day: date
    booking_id: int
    starts_at: str  # текстом, чтобы не спорить о tz в UI
    ends_at: str
    title: str
    kind: str               # PD/GZ
    tenant_name: str
    gz_group_name: str


@dataclass(frozen=True)
class UnitAvailability:
    venue_unit_id: int
    venue_unit_name: str
    venue_unit_code: str
    conflict_count: int
    conflict_days_sample: List[date]
    conflicts_sample: List[SlotConflict]


def get_units_availability_for_rule(
    *,
    venue_id: int,
    venue_unit_ids: List[int],
    weekday: int,           # 1..7 ISO
    starts_at: time,
    ends_at: time,
    valid_from: date,
    valid_to: date,
    tz_name: str = "Europe/Moscow",
    sample_days_limit: int = 10,
    sample_conflicts_limit: int = 20,
) -> List[UnitAvailability]:
    if ends_at <= starts_at:
        raise ValueError("ends_at должен быть позже starts_at")
    if valid_to < valid_from:
        raise ValueError("valid_to не может быть раньше valid_from")
    if not (1 <= int(weekday) <= 7):
        raise ValueError("weekday должен быть 1..7")
    venue_unit_ids = [int(x) for x in venue_unit_ids if x is not None]

    if not venue_unit_ids:
        return []

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1) конфликты по датам и кем занято (семпл)
            sql = """
WITH days AS (
  SELECT d::date AS day
  FROM generate_series(%(from)s::date, %(to)s::date, interval '1 day') AS d
  WHERE extract(isodow from d) = %(weekday)s
),
slots AS (
  SELECT
    day,
    ((day::timestamp + %(start)s::time) AT TIME ZONE %(tz)s)::timestamptz AS slot_start,
    ((day::timestamp + %(end)s::time)   AT TIME ZONE %(tz)s)::timestamptz AS slot_end
  FROM days
),
c AS (
  SELECT
    b.venue_unit_id,
    s.day,
    b.id AS booking_id,
    to_char(b.starts_at AT TIME ZONE %(tz)s, 'HH24:MI') AS b_start,
    to_char(b.ends_at   AT TIME ZONE %(tz)s, 'HH24:MI') AS b_end,
    b.title,
    b.activity::text AS kind,
    COALESCE(t.name, '') AS tenant_name,
    COALESCE(gc.full_name || ' — ' || gg.group_year::text, '') AS gz_group_name
  FROM slots s
  JOIN public.bookings b
    ON b.status <> 'cancelled'
   AND b.venue_id = %(venue_id)s
   AND b.venue_unit_id = ANY(%(unit_ids)s)
   AND b.starts_at < s.slot_end
   AND b.ends_at   > s.slot_start
  LEFT JOIN public.tenants t ON t.id = b.tenant_id
  LEFT JOIN public.gz_groups gg ON gg.id = b.gz_group_id
  LEFT JOIN public.gz_coaches gc ON gc.id = gg.coach_id
),
agg AS (
  SELECT
    venue_unit_id,
    COUNT(*) AS conflict_count,
    ARRAY_AGG(day ORDER BY day)[:%(days_limit)s] AS conflict_days_sample
  FROM c
  GROUP BY venue_unit_id
),
sample AS (
  SELECT *
  FROM c
  ORDER BY day, booking_id
  LIMIT %(conf_limit)s
)
SELECT
  vu.id AS venue_unit_id,
  COALESCE(vu.name, '') AS venue_unit_name,
  COALESCE(vu.code, '') AS venue_unit_code,
  COALESCE(a.conflict_count, 0) AS conflict_count,
  COALESCE(a.conflict_days_sample, ARRAY[]::date[]) AS conflict_days_sample,
  COALESCE(
    (
      SELECT json_agg(json_build_object(
        'day', s.day,
        'booking_id', s.booking_id,
        'starts_at', s.b_start,
        'ends_at', s.b_end,
        'title', s.title,
        'kind', s.kind,
        'tenant_name', s.tenant_name,
        'gz_group_name', s.gz_group_name
      ))
      FROM sample s
      WHERE s.venue_unit_id = vu.id
    ),
    '[]'::json
  ) AS conflicts_sample
FROM public.venue_units vu
LEFT JOIN agg a ON a.venue_unit_id = vu.id
WHERE vu.venue_id = %(venue_id)s
  AND vu.id = ANY(%(unit_ids)s)
ORDER BY vu.sort_order, vu.code, vu.name;
"""
            cur.execute(
                sql,
                {
                    "venue_id": int(venue_id),
                    "unit_ids": venue_unit_ids,
                    "weekday": int(weekday),
                    "start": starts_at,
                    "end": ends_at,
                    "from": valid_from,
                    "to": valid_to,
                    "tz": tz_name,
                    "days_limit": int(sample_days_limit),
                    "conf_limit": int(sample_conflicts_limit),
                },
            )
            rows = cur.fetchall()

        out: List[UnitAvailability] = []
        for r in rows:
            conflicts_json: List[Dict[str, Any]] = r["conflicts_sample"] or []
            conflicts = [
                SlotConflict(
                    day=x["day"],
                    booking_id=int(x["booking_id"]),
                    starts_at=str(x["starts_at"]),
                    ends_at=str(x["ends_at"]),
                    title=str(x.get("title") or ""),
                    kind=str(x.get("kind") or ""),
                    tenant_name=str(x.get("tenant_name") or ""),
                    gz_group_name=str(x.get("gz_group_name") or ""),
                )
                for x in conflicts_json
            ]
            out.append(
                UnitAvailability(
                    venue_unit_id=int(r["venue_unit_id"]),
                    venue_unit_name=str(r.get("venue_unit_name") or ""),
                    venue_unit_code=str(r.get("venue_unit_code") or ""),
                    conflict_count=int(r.get("conflict_count") or 0),
                    conflict_days_sample=list(r.get("conflict_days_sample") or []),
                    conflicts_sample=conflicts,
                )
            )
        return out
    finally:
        if conn:
            put_conn(conn)
