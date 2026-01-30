from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class UsageRow:
    org_id: int
    org_name: str
    venue_id: int
    venue_name: str

    capacity_sec: int

    pd_sec: int
    gz_sec: int
    total_sec: int

    morning_capacity_sec: int
    day_capacity_sec: int
    evening_capacity_sec: int

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


def _sec_between(t0: time, t1: time) -> int:
    # ВАЖНО: предполагаем t1 > t0 (смены через полночь здесь не поддерживаем)
    return int((datetime.combine(date.today(), t1) - datetime.combine(date.today(), t0)).total_seconds())


def _clip_interval(a: Tuple[time, time], b: Tuple[time, time]) -> Optional[Tuple[time, time]]:
    """
    Пересечение двух time-интервалов внутри одного дня.
    Возвращает (start,end) или None.
    """
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    if e <= s:
        return None
    return s, e


def _work_window_for_org(vrow: Dict) -> Tuple[time, time]:
    """
    vrow содержит:
      org_work_start, org_work_end, org_is_24h
    """
    if bool(vrow.get("org_is_24h") or False):
        return time(0, 0), time(23, 59, 59)
    return vrow["org_work_start"], vrow["org_work_end"]


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
                    o.work_start as org_work_start,
                    o.work_end as org_work_end,
                    o.is_24h as org_is_24h,
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
                SELECT
                    v.id as venue_id,
                    v.name as venue_name,
                    v.org_id,
                    o.name as org_name,
                    o.work_start as org_work_start,
                    o.work_end as org_work_end,
                    o.is_24h as org_is_24h
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
) -> List[UsageRow]:
    """
    Теперь capacity и окно учёта берём из sport_orgs.work_start/work_end/is_24h.

    Смены считаем как пересечение:
      - утро: 08-12
      - день: 12-18
      - вечер: 18-22
    но ОБРЕЗАЕМ по рабочему окну учреждения, чтобы не накапливать секунды вне работы.
    """
    if end_day < start_day:
        raise ValueError("end_day < start_day")

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

    # Базовые смены (как у вас в UI аналитики)
    base_shift_m = (time(8, 0), time(12, 0))
    base_shift_d = (time(12, 0), time(18, 0))
    base_shift_e = (time(18, 0), time(22, 0))

    agg: Dict[int, Dict] = {}

    # init venues (включая без бронирований)
    for v in venues:
        vid = int(v["venue_id"])
        work_start, work_end = _work_window_for_org(v)

        cap_day = _sec_between(work_start, work_end)

        # shift capacities = пересечение смены с рабочим окном
        sm = _clip_interval(base_shift_m, (work_start, work_end))
        sd = _clip_interval(base_shift_d, (work_start, work_end))
        se = _clip_interval(base_shift_e, (work_start, work_end))

        cap_m = _sec_between(*sm) if sm else 0
        cap_d = _sec_between(*sd) if sd else 0
        cap_e = _sec_between(*se) if se else 0

        agg[vid] = {
            "org_id": int(v["org_id"]),
            "org_name": str(v["org_name"]),
            "venue_id": vid,
            "venue_name": str(v["venue_name"]),
            "work_start": work_start,
            "work_end": work_end,
            "shift_m": sm,
            "shift_d": sd,
            "shift_e": se,
            "capacity_sec": days_count * cap_day,
            "morning_capacity_sec": days_count * cap_m,
            "day_capacity_sec": days_count * cap_d,
            "evening_capacity_sec": days_count * cap_e,
            "pd_sec": 0,
            "gz_sec": 0,
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

        activity = (b["activity"] or "").strip().upper()
        starts_at: datetime = b["starts_at"]
        ends_at: datetime = b["ends_at"]

        work_start: time = agg[vid]["work_start"]
        work_end: time = agg[vid]["work_end"]
        sm = agg[vid]["shift_m"]
        sd = agg[vid]["shift_d"]
        se = agg[vid]["shift_e"]

        for d in _iter_days(start_day, end_day):
            work0 = datetime.combine(d, work_start, tzinfo=tz)
            work1 = datetime.combine(d, work_end, tzinfo=tz)
            work_overlap = _overlap_seconds(starts_at, ends_at, work0, work1)
            if work_overlap <= 0:
                continue

            # shift overlaps (only if shift exists inside work window)
            m_overlap = 0
            d_overlap = 0
            e_overlap = 0

            if sm:
                m0 = datetime.combine(d, sm[0], tzinfo=tz)
                m1 = datetime.combine(d, sm[1], tzinfo=tz)
                m_overlap = _overlap_seconds(starts_at, ends_at, m0, m1)

            if sd:
                d0 = datetime.combine(d, sd[0], tzinfo=tz)
                d1 = datetime.combine(d, sd[1], tzinfo=tz)
                d_overlap = _overlap_seconds(starts_at, ends_at, d0, d1)

            if se:
                e0 = datetime.combine(d, se[0], tzinfo=tz)
                e1 = datetime.combine(d, se[1], tzinfo=tz)
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
