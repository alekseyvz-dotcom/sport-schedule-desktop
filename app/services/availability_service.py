# app/services/availability_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import List, Dict, Any

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class SlotConflict:
    day: date
    booking_id: int
    who: str          # "PD: ..." / "GZ: ..."
    title: str
    starts_at: str    # 'HH:MM' local
    ends_at: str      # 'HH:MM' local


@dataclass(frozen=True)
class UnitAvailability:
    venue_unit_id: int
    unit_label: str
    conflict_count: int
    conflict_days_sample: List[date]
    conflicts_sample: List[SlotConflict]


def _to_date(x: Any) -> date:
    """
    psycopg2 может вернуть date как date или как str (например '2026-01-10').
    Приводим к date.
    """
    if isinstance(x, date):
        return x
    s = str(x or "").strip()
    return date.fromisoformat(s[:10])


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
    sample_conflicts_limit: int = 40,
) -> List[UnitAvailability]:
    if ends_at <= starts_at:
        raise ValueError("ends_at должен быть позже starts_at")
    if valid_to < valid_from:
        raise ValueError("valid_to не может быть раньше valid_from")
    if not (1 <= int(weekday) <= 7):
        raise ValueError("weekday должен быть 1..7")

    unit_ids = [int(x) for x in (venue_unit_ids or []) if x is not None]
    if not unit_ids:
        return []

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
    (ARRAY_AGG(day ORDER BY day))[1:%(days_limit)s] AS conflict_days_sample
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
  COALESCE(NULLIF(vu.code, ''), vu.name, ('unit#' || vu.id::text)) AS unit_label,
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
                    "unit_ids": unit_ids,
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
            # days могут прийти как date[] или как list[str]
            days_raw = list(r.get("conflict_days_sample") or [])
            days = [_to_date(x) for x in days_raw]

            conflicts_json: List[Dict[str, Any]] = r.get("conflicts_sample") or []
            conflicts: List[SlotConflict] = []

            for x in conflicts_json:
                kind = str(x.get("kind") or "")
                tenant_name = str(x.get("tenant_name") or "").strip()
                gz_group_name = str(x.get("gz_group_name") or "").strip()
                who = f"PD: {tenant_name}" if kind == "PD" else f"GZ: {gz_group_name}"

                conflicts.append(
                    SlotConflict(
                        day=_to_date(x.get("day")),
                        booking_id=int(x["booking_id"]),
                        who=who.strip(),
                        title=str(x.get("title") or ""),
                        starts_at=str(x.get("starts_at") or ""),
                        ends_at=str(x.get("ends_at") or ""),
                    )
                )

            out.append(
                UnitAvailability(
                    venue_unit_id=int(r["venue_unit_id"]),
                    unit_label=str(r.get("unit_label") or ""),
                    conflict_count=int(r.get("conflict_count") or 0),
                    conflict_days_sample=days,
                    conflicts_sample=conflicts,
                )
            )

        return out
    finally:
        if conn:
            put_conn(conn)
