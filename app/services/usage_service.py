from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class UsageRow:
    org_id: int
    org_name: str
    venue_id: int
    venue_name: str

    # capacity for whole work window (08-22) across days
    capacity_sec: int

    pd_sec: int
    gz_sec: int
    total_sec: int

    # capacities per shift across days
    morning_capacity_sec: int  # 08-12
    day_capacity_sec: int      # 12-18
    evening_capacity_sec: int  # 18-22

    # totals per shift
    morning_pd_sec: int
    morning_gz_sec: int
    morning_total_sec: int

    day_pd_sec: int
    day_gz_sec: int
    day_total_sec: int

    evening_pd_sec: int
    evening_gz_sec: int
    evening_total_sec: int


def _overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    s = max(a0, b0)
    e = min(a1, b1)
    if e <= s:
        return 0
    return int((e - s).total_seconds())


def _iter_days(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


def _load_bookings_for_range(
    *,
    start_dt: datetime,
    end_dt: datetime,
    org_id: Optional[int],
    include_cancelled: bool,
) -> List[Dict]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT
                    b.id,
                    b.venue_id,
                    v.name as venue_name,
                    v.org_id,
                    o.name as org_name,
                    b.activity,
                    b.status,
                    b.starts_at,
                    b.ends_at
                FROM public.bookings b
                JOIN public.venues v ON v.id = b.venue_id
                JOIN public.sport_orgs o ON o.id = v.org_id
                WHERE b.starts_at < %(end_dt)s
                  AND b.ends_at > %(start_dt)s
            """
            params = {"start_dt": start_dt, "end_dt": end_dt}
            if not include_cancelled:
                sql += " AND b.status <> 'cancelled'"
            if org_id is not None:
                sql += " AND v.org_id = %(org_id)s"
                params["org_id"] = int(org_id)

            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        if conn:
            put_conn(conn)


def _load_venues(org_id: Optional[int]) -> List[Dict]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT v.id as venue_id, v.name as venue_name, v.org_id, o.name as org_name
                FROM public.venues v
                JOIN public.sport_orgs o ON o.id = v.org_id
                WHERE v.is_active = true
            """
            params = {}
            if org_id is not None:
                sql += " AND v.org_id = %(org_id)s"
                params["org_id"] = int(org_id)
            sql += " ORDER BY o.name, v.name"
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        if conn:
            put_conn(conn)


def calc_usage_by_venues(
    *,
    start_day: date,
    end_day: date,
    tz: timezone,
    org_id: Optional[int] = None,
    include_cancelled: bool = False,
    work_start: time = time(8, 0),
    work_end: time = time(22, 0),
) -> List[UsageRow]:
    """
    Считает загрузку по площадкам (venues) за период дат (включительно),
    в рабочем окне 08-22, и в разрезе смен:
      - утро 08-12
      - день 12-18
      - вечер 18-22
    Считает отдельно ПД/ГЗ по каждой смене.
    """
    if end_day < start_day:
        raise ValueError("end_day < start_day")

    # Диапазон для выборки пересечений
    range_start_dt = datetime.combine(start_day, time(0, 0), tzinfo=tz)
    range_end_dt = datetime.combine(end_day + timedelta(days=1), time(0, 0), tzinfo=tz)

    venues = _load_venues(org_id)
    bookings = _load_bookings_for_range(
        start_dt=range_start_dt,
        end_dt=range_end_dt,
        org_id=org_id,
        include_cancelled=include_cancelled,
    )

    days_count = (end_day - start_day).days + 1

    def _sec_between(t0: time, t1: time) -> int:
        return int((datetime.combine(date.today(), t1) - datetime.combine(date.today(), t0)).total_seconds())

    # shifts (внутри рабочего окна)
    shift_m = (time(8, 0), time(12, 0))
    shift_d = (time(12, 0), time(18, 0))
    shift_e = (time(18, 0), time(22, 0))

    # capacities per day
    cap_day = _sec_between(work_start, work_end)
    cap_m = _sec_between(shift_m[0], shift_m[1])
    cap_d = _sec_between(shift_d[0], shift_d[1])
    cap_e = _sec_between(shift_e[0], shift_e[1])

    # base aggregates (включая venues без бронирований)
    agg: Dict[int, Dict] = {}
    for v in venues:
        vid = int(v["venue_id"])
        agg[vid] = {
            "org_id": int(v["org_id"]),
            "org_name": str(v["org_name"]),
            "venue_id": vid,
            "venue_name": str(v["venue_name"]),
            "capacity_sec": days_count * cap_day,
            "morning_capacity_sec": days_count * cap_m,
            "day_capacity_sec": days_count * cap_d,
            "evening_capacity_sec": days_count * cap_e,
            # totals
            "pd_sec": 0,
            "gz_sec": 0,
            # shift split PD/GZ
            "morning_pd_sec": 0,
            "morning_gz_sec": 0,
            "day_pd_sec": 0,
            "day_gz_sec": 0,
            "evening_pd_sec": 0,
            "evening_gz_sec": 0,
        }

    for b in bookings:
        vid = int(b["venue_id"])
        if vid not in agg:
            continue

        activity = (b["activity"] or "").strip()  # 'PD' or 'GZ'
        starts_at: datetime = b["starts_at"]
        ends_at: datetime = b["ends_at"]

        # режем по дням для корректного разнесения
        for d in _iter_days(start_day, end_day):
            work0 = datetime.combine(d, work_start, tzinfo=tz)
            work1 = datetime.combine(d, work_end, tzinfo=tz)
            work_overlap = _overlap_seconds(starts_at, ends_at, work0, work1)
            if work_overlap <= 0:
                continue

            # shifts intervals
            m0 = datetime.combine(d, shift_m[0], tzinfo=tz)
            m1 = datetime.combine(d, shift_m[1], tzinfo=tz)
            d0 = datetime.combine(d, shift_d[0], tzinfo=tz)
            d1 = datetime.combine(d, shift_d[1], tzinfo=tz)
            e0 = datetime.combine(d, shift_e[0], tzinfo=tz)
            e1 = datetime.combine(d, shift_e[1], tzinfo=tz)

            m_overlap = _overlap_seconds(starts_at, ends_at, m0, m1)
            d_overlap = _overlap_seconds(starts_at, ends_at, d0, d1)
            e_overlap = _overlap_seconds(starts_at, ends_at, e0, e1)

            if activity == "PD":
                agg[vid]["pd_sec"] += work_overlap
                agg[vid]["morning_pd_sec"] += m_overlap
                agg[vid]["day_pd_sec"] += d_overlap
                agg[vid]["evening_pd_sec"] += e_overlap
            elif activity == "GZ":
                agg[vid]["gz_sec"] += work_overlap
                agg[vid]["morning_gz_sec"] += m_overlap
                agg[vid]["day_gz_sec"] += d_overlap
                agg[vid]["evening_gz_sec"] += e_overlap
            else:
                # неизвестный тип активности: игнорируем для PD/GZ, но и в total тогда не попадёт
                pass

    out: List[UsageRow] = []
    for vid, a in agg.items():
        pd_sec = int(a["pd_sec"])
        gz_sec = int(a["gz_sec"])
        total_sec = pd_sec + gz_sec

        morning_pd = int(a["morning_pd_sec"])
        morning_gz = int(a["morning_gz_sec"])
        day_pd = int(a["day_pd_sec"])
        day_gz = int(a["day_gz_sec"])
        evening_pd = int(a["evening_pd_sec"])
        evening_gz = int(a["evening_gz_sec"])

        out.append(
            UsageRow(
                org_id=int(a["org_id"]),
                org_name=str(a["org_name"]),
                venue_id=int(a["venue_id"]),
                venue_name=str(a["venue_name"]),
                capacity_sec=int(a["capacity_sec"]),
                pd_sec=pd_sec,
                gz_sec=gz_sec,
                total_sec=total_sec,
                morning_capacity_sec=int(a["morning_capacity_sec"]),
                day_capacity_sec=int(a["day_capacity_sec"]),
                evening_capacity_sec=int(a["evening_capacity_sec"]),
                morning_pd_sec=morning_pd,
                morning_gz_sec=morning_gz,
                morning_total_sec=morning_pd + morning_gz,
                day_pd_sec=day_pd,
                day_gz_sec=day_gz,
                day_total_sec=day_pd + day_gz,
                evening_pd_sec=evening_pd,
                evening_gz_sec=evening_gz,
                evening_total_sec=evening_pd + evening_gz,
            )
        )

    out.sort(key=lambda r: (r.total_sec / r.capacity_sec) if r.capacity_sec else 0.0, reverse=True)
    return out
