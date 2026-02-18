from __future__ import annotations

from datetime import date, time, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2.extras import RealDictCursor

from web.deps import get_db, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

TZ = timezone(timedelta(hours=3))


# ── helpers ──

def _has_permission(conn, user_id: int, perm_code: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM app_user_permissions WHERE user_id = %s AND perm_code = %s",
            (user_id, perm_code),
        )
        return cur.fetchone() is not None


def _pct(sec: int, cap: int) -> float:
    return 0.0 if cap <= 0 else round(100.0 * sec / cap, 1)


def _hours(sec: int) -> float:
    return round(sec / 3600.0, 1)


def _sec_between(t0: time, t1: time) -> int:
    from datetime import datetime, date as d
    return int((datetime.combine(d.today(), t1) - datetime.combine(d.today(), t0)).total_seconds())


def _clip(a: Tuple[time, time], b: Tuple[time, time]):
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    return (s, e) if e > s else None


def _unit_fraction(code: Optional[str]) -> float:
    c = (code or "").strip().upper()
    if c.startswith("Q"):
        return 0.25
    if c.startswith("H"):
        return 0.5
    return 1.0


def _weighted_busy_seconds(intervals) -> int:
    from datetime import datetime
    events = []
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


def _iter_days(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


def _period_range(anchor: date, period: str):
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = anchor.replace(day=1)
        nm = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, nm - timedelta(days=1)
    if period == "quarter":
        q = (anchor.month - 1) // 3
        sm = q * 3 + 1
        start = anchor.replace(month=sm, day=1)
        nq = start.replace(year=start.year + 1, month=1) if sm == 10 else start.replace(month=sm + 3)
        return start, nq - timedelta(days=1)
    if period == "year":
        return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31)
    return anchor, anchor


def _load_orgs(conn, user: dict) -> list:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user["role_code"] == "admin":
            cur.execute(
                "SELECT id, name FROM sport_orgs WHERE is_active = true ORDER BY name"
            )
        else:
            cur.execute(
                """
                SELECT o.id, o.name
                FROM sport_orgs o
                JOIN app_user_org_permissions p ON p.org_id = o.id
                WHERE p.user_id = %s AND p.can_view = true AND o.is_active = true
                ORDER BY o.name
                """,
                (user["id"],),
            )
        return cur.fetchall()


def _load_venues(conn, org_id: Optional[int], user: dict) -> list:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        sql = """
            SELECT v.id AS venue_id, v.name AS venue_name, v.org_id,
                   o.name AS org_name, o.work_start, o.work_end, o.is_24h
            FROM venues v
            JOIN sport_orgs o ON o.id = v.org_id
            WHERE v.is_active = true
        """
        params = {}
        if org_id:
            sql += " AND v.org_id = %(org_id)s"
            params["org_id"] = org_id
        elif user["role_code"] != "admin":
            sql += """
                AND v.org_id IN (
                    SELECT org_id FROM app_user_org_permissions
                    WHERE user_id = %(uid)s AND can_view = true
                )
            """
            params["uid"] = user["id"]
        sql += " ORDER BY o.name, v.name"
        cur.execute(sql, params)
        return cur.fetchall()


def _load_bookings(conn, start_dt, end_dt, org_id, user, include_cancelled):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        sql = """
            SELECT b.id, b.venue_id, b.venue_unit_id, u.code AS unit_code,
                   b.activity, b.starts_at, b.ends_at, v.org_id
            FROM bookings b
            JOIN venues v ON v.id = b.venue_id
            LEFT JOIN venue_units u ON u.id = b.venue_unit_id
            WHERE b.starts_at < %(end)s AND b.ends_at > %(start)s
        """
        params = {"start": start_dt, "end": end_dt}
        if not include_cancelled:
            sql += " AND b.status <> 'cancelled'"
        if org_id:
            sql += " AND v.org_id = %(org_id)s"
            params["org_id"] = org_id
        elif user["role_code"] != "admin":
            sql += """
                AND v.org_id IN (
                    SELECT org_id FROM app_user_org_permissions
                    WHERE user_id = %(uid)s AND can_view = true
                )
            """
            params["uid"] = user["id"]
        cur.execute(sql, params)
        return cur.fetchall()


def _calc_usage(venues, bookings, start_day, end_day):
    from datetime import datetime

    SHIFT_M = (time(8, 0), time(12, 0))
    SHIFT_D = (time(12, 0), time(18, 0))
    SHIFT_E = (time(18, 0), time(22, 0))

    days_count = (end_day - start_day).days + 1

    agg = {}
    for v in venues:
        vid = int(v["venue_id"])
        ws = time(0, 0) if v["is_24h"] else v["work_start"]
        we = time(23, 59, 59) if v["is_24h"] else v["work_end"]
        cap_day = _sec_between(ws, we)
        sm = _clip(SHIFT_M, (ws, we))
        sd = _clip(SHIFT_D, (ws, we))
        se = _clip(SHIFT_E, (ws, we))

        agg[vid] = {
            "org_id": int(v["org_id"]), "org_name": v["org_name"],
            "venue_id": vid, "venue_name": v["venue_name"],
            "ws": ws, "we": we, "sm": sm, "sd": sd, "se": se,
            "capacity_sec": days_count * cap_day,
            "m_cap": days_count * (_sec_between(*sm) if sm else 0),
            "d_cap": days_count * (_sec_between(*sd) if sd else 0),
            "e_cap": days_count * (_sec_between(*se) if se else 0),
            "pd_sec": 0, "gz_sec": 0,
            "m_pd": 0, "m_gz": 0, "d_pd": 0, "d_gz": 0, "e_pd": 0, "e_gz": 0,
        }

    iw = defaultdict(list)
    im = defaultdict(list)
    id_ = defaultdict(list)
    ie = defaultdict(list)

    for b in bookings:
        vid = int(b["venue_id"])
        if vid not in agg:
            continue
        act = (b["activity"] or "").upper()
        if act not in ("PD", "GZ"):
            continue
        frac = _unit_fraction(b.get("unit_code"))
        a = agg[vid]

        for d in _iter_days(start_day, end_day):
            w0 = datetime.combine(d, a["ws"], tzinfo=TZ)
            w1 = datetime.combine(d, a["we"], tzinfo=TZ)
            s = max(b["starts_at"], w0)
            e = min(b["ends_at"], w1)
            if e <= s:
                continue
            iw[(vid, d, act)].append((s, e, frac))

            if a["sm"]:
                ms = max(b["starts_at"], datetime.combine(d, a["sm"][0], tzinfo=TZ))
                me = min(b["ends_at"], datetime.combine(d, a["sm"][1], tzinfo=TZ))
                if me > ms:
                    im[(vid, d, act)].append((ms, me, frac))
            if a["sd"]:
                ds = max(b["starts_at"], datetime.combine(d, a["sd"][0], tzinfo=TZ))
                de = min(b["ends_at"], datetime.combine(d, a["sd"][1], tzinfo=TZ))
                if de > ds:
                    id_[(vid, d, act)].append((ds, de, frac))
            if a["se"]:
                es = max(b["starts_at"], datetime.combine(d, a["se"][0], tzinfo=TZ))
                ee = min(b["ends_at"], datetime.combine(d, a["se"][1], tzinfo=TZ))
                if ee > es:
                    ie[(vid, d, act)].append((es, ee, frac))

    for vid in agg:
        for d in _iter_days(start_day, end_day):
            agg[vid]["pd_sec"] += _weighted_busy_seconds(iw.get((vid, d, "PD"), []))
            agg[vid]["gz_sec"] += _weighted_busy_seconds(iw.get((vid, d, "GZ"), []))
            agg[vid]["m_pd"] += _weighted_busy_seconds(im.get((vid, d, "PD"), []))
            agg[vid]["m_gz"] += _weighted_busy_seconds(im.get((vid, d, "GZ"), []))
            agg[vid]["d_pd"] += _weighted_busy_seconds(id_.get((vid, d, "PD"), []))
            agg[vid]["d_gz"] += _weighted_busy_seconds(id_.get((vid, d, "GZ"), []))
            agg[vid]["e_pd"] += _weighted_busy_seconds(ie.get((vid, d, "PD"), []))
            agg[vid]["e_gz"] += _weighted_busy_seconds(ie.get((vid, d, "GZ"), []))

    return agg


def _build_result(agg):
    by_org = defaultdict(list)
    for a in agg.values():
        by_org[(a["org_id"], a["org_name"])].append(a)

    result = []
    for (oid, oname), venues in sorted(by_org.items(), key=lambda x: x[0][1]):
        org_cap = sum(v["capacity_sec"] for v in venues)
        org_pd = sum(v["pd_sec"] for v in venues)
        org_gz = sum(v["gz_sec"] for v in venues)
        org_busy = org_pd + org_gz
        org_pct = _pct(org_busy, org_cap)

        org_entry = {
            "org_id": oid, "org_name": oname,
            "is_total": True,
            "pct": org_pct,
            "pd_pct": _pct(org_pd, org_cap),
            "gz_pct": _pct(org_gz, org_cap),
            "pd_h": _hours(org_pd),
            "gz_h": _hours(org_gz),
            "busy_h": _hours(org_busy),
            "cap_h": _hours(org_cap),
            "m_cap": sum(v["m_cap"] for v in venues),
            "m_pd": sum(v["m_pd"] for v in venues),
            "m_gz": sum(v["m_gz"] for v in venues),
            "d_cap": sum(v["d_cap"] for v in venues),
            "d_pd": sum(v["d_pd"] for v in venues),
            "d_gz": sum(v["d_gz"] for v in venues),
            "e_cap": sum(v["e_cap"] for v in venues),
            "e_pd": sum(v["e_pd"] for v in venues),
            "e_gz": sum(v["e_gz"] for v in venues),
        }
        result.append(org_entry)

        venues.sort(key=lambda v: _pct(v["pd_sec"] + v["gz_sec"], v["capacity_sec"]), reverse=True)
        for v in venues:
            busy = v["pd_sec"] + v["gz_sec"]
            result.append({
                "org_id": oid, "org_name": oname,
                "venue_id": v["venue_id"], "venue_name": v["venue_name"],
                "is_total": False,
                "pct": _pct(busy, v["capacity_sec"]),
                "pd_pct": _pct(v["pd_sec"], v["capacity_sec"]),
                "gz_pct": _pct(v["gz_sec"], v["capacity_sec"]),
                "pd_h": _hours(v["pd_sec"]),
                "gz_h": _hours(v["gz_sec"]),
                "busy_h": _hours(busy),
                "cap_h": _hours(v["capacity_sec"]),
                "m_cap": v["m_cap"], "m_pd": v["m_pd"], "m_gz": v["m_gz"],
                "d_cap": v["d_cap"], "d_pd": v["d_pd"], "d_gz": v["d_gz"],
                "e_cap": v["e_cap"], "e_pd": v["e_pd"], "e_gz": v["e_gz"],
            })

    # Sort by org total pct desc
    org_pcts = {}
    for r in result:
        if r["is_total"]:
            org_pcts[r["org_id"]] = r["pct"]

    final = []
    org_groups = defaultdict(list)
    for r in result:
        org_groups[r["org_id"]].append(r)

    for oid in sorted(org_pcts, key=org_pcts.get, reverse=True):
        final.extend(org_groups[oid])

    return final


# ── route ──

@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request,
    org_id: Optional[str] = Query(None),
    day: Optional[str] = Query(None),
    period: str = Query("month"),
    show_cancelled: bool = Query(False),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    # Проверка прав
    is_admin = user["role_code"] == "admin"
    has_perm = is_admin or _has_permission(conn, user["id"], "page.analytics") or _has_permission(conn, user["id"], "tab.analytics")

    if not has_perm:
        raise HTTPException(403, "Нет доступа к аналитике")

    # org_id: "" → None, "5" → 5
    if org_id is not None:
        org_id = org_id.strip()
        if org_id == "" or org_id.lower() == "none":
            org_id = None
        else:
            try:
                org_id = int(org_id)
            except ValueError:
                org_id = None

    orgs = _load_orgs(conn, user)

    try:
        anchor = date.fromisoformat(day) if day else date.today()
    except ValueError:
        anchor = date.today()

    period = period if period in ("day", "week", "month", "quarter", "year") else "month"
    d0, d1 = _period_range(anchor, period)

    from datetime import datetime
    start_dt = datetime.combine(d0, time(0, 0), tzinfo=TZ)
    end_dt = datetime.combine(d1 + timedelta(days=1), time(0, 0), tzinfo=TZ)

    venues = _load_venues(conn, org_id, user)
    bookings = _load_bookings(conn, start_dt, end_dt, org_id, user, show_cancelled)
    agg = _calc_usage(venues, bookings, d0, d1)
    rows = _build_result(agg)

    # Общие итоги
    total_cap = sum(a["capacity_sec"] for a in agg.values())
    total_pd = sum(a["pd_sec"] for a in agg.values())
    total_gz = sum(a["gz_sec"] for a in agg.values())
    total_busy = total_pd + total_gz

    period_label = f"{d0:%d.%m.%Y} – {d1:%d.%m.%Y}"

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "user": user,
        "orgs": orgs,
        "org_id": org_id,
        "anchor": anchor.isoformat(),
        "period": period,
        "show_cancelled": show_cancelled,
        "period_label": period_label,
        "rows": rows,
        "total_pct": _pct(total_busy, total_cap),
        "total_pd_pct": _pct(total_pd, total_cap),
        "total_gz_pct": _pct(total_gz, total_cap),
        "total_pd_h": _hours(total_pd),
        "total_gz_h": _hours(total_gz),
        "total_busy_h": _hours(total_busy),
        "total_cap_h": _hours(total_cap),
        "has_analytics": True,
    })
