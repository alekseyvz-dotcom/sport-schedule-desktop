from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple, DefaultDict
from collections import defaultdict

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.core.day_parts_settings import DayPartsSettings
from app.services.day_parts_settings_service import get_day_parts_settings


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


def _iter_days(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


def _sec_between(t0: time, t1: time) -> int:
    return int((datetime.combine(date.today(), t1) - datetime.combine(date.today(), t0)).total_seconds())


def _clip_interval(a: Tuple[time, time], b: Tuple[time, time]) -> Optional[Tuple[time, time]]:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    if e <= s:
        return None
    return s, e


def _work_window_for_org(vrow: Dict) -> Tuple[time, time]:
    if bool(vrow.get("org_is_24h") or False):
        return time(0, 0), time(23, 59, 59)
    return vrow["org_work_start"], vrow["org_work_end"]


def _unit_fraction(unit_code: Optional[str]) -> float:
    """
    Доля площадки, занимаемая юнитом:
      Q1..Q4 => 0.25
      H1/H2  => 0.5
      main/NULL/прочее => 1.0
    """
    code = (unit_code or "").strip().upper()
    if code.startswith("Q"):
        return 0.25
    if code.startswith("H"):
        return 0.5
    return 1.0


def _weighted_busy_seconds(intervals: List[Tuple[datetime, datetime, float]]) -> int:
    """
    intervals: [(start_dt, end_dt, fraction)]
    Возвращает занятость целой площадки в секундах:
    сумма fraction по пересечениям клипается до 1.0.
    """
    events: List[Tuple[datetime, float]] = []
    for s, e, f in intervals:
        if e <= s or f <= 0:
            continue
        events.append((s, +f))
        events.append((e, -f))

    if not events:
        return 0

    events.sort(key=lambda x: x[0])

    busy = 0.0
    total = 0.0
    prev_t = events[0][0]
    i = 0

    while i < len(events):
        t = events[i][0]

        if t > prev_t:
            sec = (t - prev_t).total_seconds()
            if sec > 0:
                total += min(1.0, max(0.0, busy)) * sec
            prev_t = t

        while i < len(events) and events[i][0] == t:
            busy += events[i][1]
            i += 1

    return int(total)


def _validate_shift_order(
    m: Tuple[time, time],
    d: Tuple[time, time],
    e: Tuple[time, time],
) -> None:
    if not (m[0] < m[1]):
        raise ValueError("Некорректный интервал 'утро'")
    if not (d[0] < d[1]):
        raise ValueError("Некорректный интервал 'день'")
    if not (e[0] < e[1]):
        raise ValueError("Некорректный интервал 'вечер'")
    if m[1] > d[0]:
        raise ValueError("Интервалы 'утро' и 'день' пересекаются")
    if d[1] > e[0]:
        raise ValueError("Интервалы 'день' и 'вечер' пересекаются")


def _resolve_day_parts(
    day_parts: Optional[DayPartsSettings],
    base_shift_m: Optional[Tuple[time, time]],
    base_shift_d: Optional[Tuple[time, time]],
    base_shift_e: Optional[Tuple[time, time]],
) -> Tuple[Tuple[time, time], Tuple[time, time], Tuple[time, time]]:
    if day_parts is None:
        day_parts = get_day_parts_settings()

    m = base_shift_m or day_parts.morning_interval()
    d = base_shift_d or day_parts.day_interval()
    e = base_shift_e or day_parts.evening_interval()

    _validate_shift_order(m, d, e)
    return m, d, e


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
                    b.venue_unit_id,
                    u.code AS unit_code,
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
                LEFT JOIN public.venue_units u ON u.id = b.venue_unit_id
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


def _load_open_days_map(
    *,
    start_day: date,
    end_day: date,
    org_id: Optional[int],
) -> Dict[Tuple[int, date], bool]:
    """
    (venue_id, day) -> открыто ли в этот день

    Открыто = в сезоне AND нет закрытия учреждения AND нет закрытия площадки.
    Если сезон не задан (и нет шаблонов) - is_venue_in_season вернёт true -> круглый год.
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            org_filter = ""
            params = {"d0": start_day, "d1": end_day}
            if org_id is not None:
                org_filter = " AND v.org_id = %(org_id)s"
                params["org_id"] = int(org_id)

            sql = f"""
                WITH vs AS (
                    SELECT v.id AS venue_id, v.org_id
                    FROM public.venues v
                    WHERE v.is_active = true
                    {org_filter}
                ),
                days AS (
                    SELECT d::date AS day
                    FROM generate_series(%(d0)s::date, %(d1)s::date, interval '1 day') d
                )
                SELECT
                    vs.venue_id,
                    days.day,
                    (
                      public.is_venue_in_season(vs.venue_id, days.day)
                      AND NOT EXISTS (
                        SELECT 1
                        FROM public.org_closures oc
                        WHERE oc.is_active = true
                          AND oc.org_id = vs.org_id
                          AND days.day BETWEEN oc.date_from AND oc.date_to
                      )
                      AND NOT EXISTS (
                        SELECT 1
                        FROM public.venue_closures vc
                        WHERE vc.is_active = true
                          AND vc.venue_id = vs.venue_id
                          AND days.day BETWEEN vc.date_from AND vc.date_to
                      )
                    ) AS is_open
                FROM vs
                CROSS JOIN days
            """
            cur.execute(sql, params)
            rows = cur.fetchall()

            out: Dict[Tuple[int, date], bool] = {}
            for r in rows:
                out[(int(r["venue_id"]), r["day"])] = bool(r["is_open"])
            return out
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
    day_parts: Optional[DayPartsSettings] = None,
    base_shift_m: Optional[Tuple[time, time]] = None,
    base_shift_d: Optional[Tuple[time, time]] = None,
    base_shift_e: Optional[Tuple[time, time]] = None,
) -> List[UsageRow]:
    """
    Аналитика по площадкам (venues).

    Считает занятость ЦЕЛОЙ площадки, учитывая что брони могут быть по четвертям/половинам:
      - Q1..Q4 => 0.25
      - H1/H2  => 0.5
      - main или venue_unit_id NULL => 1.0

    Если в один и тот же интервал занято несколько юнитов, доли суммируются и клипаются до 1.0,
    поэтому процент не завышается.

    ВАЖНО: capacity считается только по дням, когда площадка ОТКРЫТА
    (учитывается сезонность + закрытия org/venue).

    Интервалы morning/day/evening берутся из day_parts.
    Если day_parts не передан — подгружаются из settings.dat.
    """
    if end_day < start_day:
        raise ValueError("end_day < start_day")

    base_shift_m, base_shift_d, base_shift_e = _resolve_day_parts(
        day_parts=day_parts,
        base_shift_m=base_shift_m,
        base_shift_d=base_shift_d,
        base_shift_e=base_shift_e,
    )

    range_start_dt = datetime.combine(start_day, time(0, 0), tzinfo=tz)
    range_end_dt = datetime.combine(end_day + timedelta(days=1), time(0, 0), tzinfo=tz)

    venues = _load_venues(org_id)
    open_days_map = _load_open_days_map(start_day=start_day, end_day=end_day, org_id=org_id)

    bookings = _load_bookings_for_range(
        start_dt=range_start_dt,
        end_dt=range_end_dt,
        org_id=org_id,
        include_cancelled=include_cancelled,
    )

    agg: Dict[int, Dict] = {}

    # init venues (включая без бронирований)
    for v in venues:
        vid = int(v["venue_id"])
        work_start, work_end = _work_window_for_org(v)

        cap_day = _sec_between(work_start, work_end)

        sm = _clip_interval(base_shift_m, (work_start, work_end))
        sd = _clip_interval(base_shift_d, (work_start, work_end))
        se = _clip_interval(base_shift_e, (work_start, work_end))

        cap_m = _sec_between(*sm) if sm else 0
        cap_d = _sec_between(*sd) if sd else 0
        cap_e = _sec_between(*se) if se else 0

        open_days_count = 0
        for d in _iter_days(start_day, end_day):
            if open_days_map.get((vid, d), True):
                open_days_count += 1

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
            "capacity_sec": open_days_count * cap_day,
            "morning_capacity_sec": open_days_count * cap_m,
            "day_capacity_sec": open_days_count * cap_d,
            "evening_capacity_sec": open_days_count * cap_e,
            "pd_sec": 0,
            "gz_sec": 0,
            "morning_pd_sec": 0,
            "morning_gz_sec": 0,
            "day_pd_sec": 0,
            "day_gz_sec": 0,
            "evening_pd_sec": 0,
            "evening_gz_sec": 0,
        }

    intervals_work: DefaultDict[tuple, list] = defaultdict(list)
    intervals_m: DefaultDict[tuple, list] = defaultdict(list)
    intervals_d: DefaultDict[tuple, list] = defaultdict(list)
    intervals_e: DefaultDict[tuple, list] = defaultdict(list)

    for b in bookings:
        vid = int(b["venue_id"])
        if vid not in agg:
            continue

        activity = (b["activity"] or "").strip().upper()
        if activity not in ("PD", "GZ"):
            continue

        starts_at: datetime = b["starts_at"]
        ends_at: datetime = b["ends_at"]
        frac = _unit_fraction(b.get("unit_code"))

        work_start: time = agg[vid]["work_start"]
        work_end: time = agg[vid]["work_end"]
        sm = agg[vid]["shift_m"]
        sd = agg[vid]["shift_d"]
        se = agg[vid]["shift_e"]

        for d in _iter_days(start_day, end_day):
            if not open_days_map.get((vid, d), True):
                continue

            work0 = datetime.combine(d, work_start, tzinfo=tz)
            work1 = datetime.combine(d, work_end, tzinfo=tz)
            s = max(starts_at, work0)
            e = min(ends_at, work1)
            if e <= s:
                continue

            intervals_work[(vid, d, activity)].append((s, e, frac))

            if sm:
                m0 = datetime.combine(d, sm[0], tzinfo=tz)
                m1 = datetime.combine(d, sm[1], tzinfo=tz)
                ms = max(starts_at, m0)
                me = min(ends_at, m1)
                if me > ms:
                    intervals_m[(vid, d, activity)].append((ms, me, frac))

            if sd:
                d0 = datetime.combine(d, sd[0], tzinfo=tz)
                d1 = datetime.combine(d, sd[1], tzinfo=tz)
                ds = max(starts_at, d0)
                de = min(ends_at, d1)
                if de > ds:
                    intervals_d[(vid, d, activity)].append((ds, de, frac))

            if se:
                e0 = datetime.combine(d, se[0], tzinfo=tz)
                e1 = datetime.combine(d, se[1], tzinfo=tz)
                es = max(starts_at, e0)
                ee = min(ends_at, e1)
                if ee > es:
                    intervals_e[(vid, d, activity)].append((es, ee, frac))

    for vid in list(agg.keys()):
        for d in _iter_days(start_day, end_day):
            if not open_days_map.get((vid, d), True):
                continue

            agg[vid]["pd_sec"] += _weighted_busy_seconds(intervals_work.get((vid, d, "PD"), []))
            agg[vid]["gz_sec"] += _weighted_busy_seconds(intervals_work.get((vid, d, "GZ"), []))

            agg[vid]["morning_pd_sec"] += _weighted_busy_seconds(intervals_m.get((vid, d, "PD"), []))
            agg[vid]["morning_gz_sec"] += _weighted_busy_seconds(intervals_m.get((vid, d, "GZ"), []))

            agg[vid]["day_pd_sec"] += _weighted_busy_seconds(intervals_d.get((vid, d, "PD"), []))
            agg[vid]["day_gz_sec"] += _weighted_busy_seconds(intervals_d.get((vid, d, "GZ"), []))

            agg[vid]["evening_pd_sec"] += _weighted_busy_seconds(intervals_e.get((vid, d, "PD"), []))
            agg[vid]["evening_gz_sec"] += _weighted_busy_seconds(intervals_e.get((vid, d, "GZ"), []))

    out: List[UsageRow] = []
    for _, a in agg.items():
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

    out = [r for r in out if r.capacity_sec > 0]
    out.sort(key=lambda r: (r.total_sec / r.capacity_sec) if r.capacity_sec else 0.0, reverse=True)
    return out
