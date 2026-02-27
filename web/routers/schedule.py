# web/routers/schedule.py
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2.extras import RealDictCursor

from web.deps import get_db, get_current_user, require_org_access, has_permission

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

TZ = timezone(timedelta(hours=3))
SLOT_MINUTES = 30


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_orgs(conn, user: dict) -> list:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user["role_code"] == "admin":
            cur.execute(
                "SELECT id, name, work_start, work_end, is_24h "
                "FROM sport_orgs WHERE is_active = true ORDER BY name"
            )
        else:
            cur.execute(
                """
                SELECT o.id, o.name, o.work_start, o.work_end, o.is_24h
                FROM sport_orgs o
                JOIN app_user_org_permissions p ON p.org_id = o.id
                WHERE p.user_id = %s AND p.can_view = true AND o.is_active = true
                ORDER BY o.name
                """,
                (user["id"],),
            )
        return cur.fetchall()


def _load_available_venue_ids_for_period(
    conn,
    venue_ids: list[int],
    date_from: date,
    date_to: date,
) -> set[int]:
    """
    Возвращает venue_id, у которых хотя бы один день в диапазоне [date_from, date_to]
    является доступным (не закрыт и в сезоне).
    Площадки, недоступные весь период — исключаются.
    """
    if not venue_ids:
        return set()

    days = []
    d = date_from
    while d <= date_to:
        days.append(d)
        d += timedelta(days=1)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        # org_id для каждой площадки
        cur.execute(
            "SELECT id, org_id FROM public.venues WHERE id = ANY(%s)",
            (venue_ids,),
        )
        venue_org: dict[int, int] = {
            row["id"]: row["org_id"] for row in cur.fetchall()
        }
        org_ids = list(set(venue_org.values()))

        # Закрытия учреждений в диапазоне
        org_closed_ranges: dict[int, list] = {}
        if org_ids:
            cur.execute(
                """
                SELECT org_id, date_from, date_to
                FROM public.org_closures
                WHERE org_id = ANY(%s)
                  AND is_active = true
                  AND date_to >= %s AND date_from <= %s
                """,
                (org_ids, date_from, date_to),
            )
            for row in cur.fetchall():
                org_closed_ranges.setdefault(row["org_id"], []).append(
                    (row["date_from"], row["date_to"])
                )

        # Закрытия площадок в диапазоне
        venue_closed_ranges: dict[int, list] = {}
        cur.execute(
            """
            SELECT venue_id, date_from, date_to
            FROM public.venue_closures
            WHERE venue_id = ANY(%s)
              AND is_active = true
              AND date_to >= %s AND date_from <= %s
            """,
            (venue_ids, date_from, date_to),
        )
        for row in cur.fetchall():
            venue_closed_ranges.setdefault(row["venue_id"], []).append(
                (row["date_from"], row["date_to"])
            )

        # Площадки с сезонными настройками
        cur.execute(
            """
            SELECT DISTINCT venue_id FROM public.venue_season_templates
            WHERE venue_id = ANY(%s) AND is_active = true
            UNION
            SELECT DISTINCT venue_id FROM public.venue_season_overrides
            WHERE venue_id = ANY(%s) AND is_active = true
            """,
            (venue_ids, venue_ids),
        )
        seasonal_ids = {row["venue_id"] for row in cur.fetchall()}

        # Пакетная проверка сезонности через БД-функцию
        season_ok: dict[tuple[int, date], bool] = {}
        seasonal_list = [vid for vid in venue_ids if vid in seasonal_ids]
        if seasonal_list:
            cur.execute(
                """
                SELECT v_id, d, public.is_venue_in_season(v_id, d) AS in_season
                FROM (
                    SELECT unnest(%s::bigint[]) AS v_id,
                           unnest(%s::date[])   AS d
                ) t
                """,
                (
                    [vid for vid in seasonal_list for _ in days],
                    [d   for _   in seasonal_list for d in days],
                ),
            )
            for row in cur.fetchall():
                season_ok[(row["v_id"], row["d"])] = bool(row["in_season"])

    # Для каждой площадки ищем хотя бы один доступный день
    available: set[int] = set()

    for vid in venue_ids:
        org_id = venue_org.get(vid)

        for d in days:
            # 1. Закрытие учреждения
            if any(
                df <= d <= dt_
                for df, dt_ in org_closed_ranges.get(org_id or -1, [])
            ):
                continue

            # 2. Закрытие площадки
            if any(
                df <= d <= dt_
                for df, dt_ in venue_closed_ranges.get(vid, [])
            ):
                continue

            # 3. Сезонность (только если настроена)
            if vid in seasonal_ids:
                if not season_ok.get((vid, d), False):
                    continue

            # Нашли доступный день — площадка включается
            available.add(vid)
            break

    return available


def _load_resources(conn, org_id: int, date_from: date, date_to: date) -> list:
    """
    Ресурсы учреждения, отфильтрованные по доступности в период [date_from, date_to].
    Площадки, закрытые или вне сезона весь период — не показываются.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT v.id AS venue_id, v.name AS venue_name,
                   vu.id AS venue_unit_id, vu.name AS unit_name,
                   vu.sort_order
            FROM venues v
            LEFT JOIN venue_units vu ON vu.venue_id = v.id AND vu.is_active = true
            WHERE v.org_id = %s AND v.is_active = true
            ORDER BY v.name, vu.sort_order NULLS FIRST, vu.name
            """,
            (org_id,),
        )
        rows = cur.fetchall()

    # Собираем все ресурсы
    all_resources = []
    seen: set[int] = set()

    for r in rows:
        if r["venue_unit_id"]:
            all_resources.append({
                "venue_id":      r["venue_id"],
                "venue_unit_id": r["venue_unit_id"],
                "name":          f"{r['venue_name']} — {r['unit_name']}",
                "short_name":    r["unit_name"],
                "venue_name":    r["venue_name"],
            })
            seen.add(r["venue_id"])
        elif r["venue_id"] not in seen:
            all_resources.append({
                "venue_id":      r["venue_id"],
                "venue_unit_id": None,
                "name":          r["venue_name"],
                "short_name":    r["venue_name"],
                "venue_name":    r["venue_name"],
            })
            seen.add(r["venue_id"])

    # Фильтруем по доступности
    all_venue_ids = list({r["venue_id"] for r in all_resources})
    try:
        available_ids = _load_available_venue_ids_for_period(
            conn, all_venue_ids, date_from, date_to
        )
    except Exception:
        # Fallback — показываем всё
        available_ids = set(all_venue_ids)

    return [r for r in all_resources if r["venue_id"] in available_ids]


def _load_bookings(
    conn,
    venue_ids: list,
    start: datetime,
    end: datetime,
    include_cancelled: bool = False,
) -> list:
    if not venue_ids:
        return []
    cancel_filter = "" if include_cancelled else "AND b.status <> 'cancelled'"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT b.id, b.venue_id, b.venue_unit_id,
                   b.activity, b.title, b.starts_at, b.ends_at,
                   b.status, b.comment,
                   b.tenant_id, b.gz_group_id,
                   t.name AS tenant_name,
                   v.name AS venue_name,
                   vu.name AS unit_name,
                   CONCAT(c.full_name, ' / ', g.group_year) AS gz_group_name,
                   COALESCE(g.is_free, false) AS gz_is_free
            FROM bookings b
            LEFT JOIN tenants t ON t.id = b.tenant_id
            LEFT JOIN gz_groups g ON g.id = b.gz_group_id
            LEFT JOIN gz_coaches c ON c.id = g.coach_id
            LEFT JOIN venues v ON v.id = b.venue_id
            LEFT JOIN venue_units vu ON vu.id = b.venue_unit_id
            WHERE b.venue_id = ANY(%s)
              AND b.starts_at < %s AND b.ends_at > %s
              {cancel_filter}
            ORDER BY b.starts_at
            """,
            (venue_ids, end, start),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# View helpers
# ---------------------------------------------------------------------------

def _time_slots(ws: time, we: time) -> list:
    slots = []
    cur = datetime.combine(date.today(), ws)
    end = datetime.combine(date.today(), we)
    while cur < end:
        slots.append(cur.time())
        cur += timedelta(minutes=SLOT_MINUTES)
    return slots


def _resolve_resource_name(b: dict) -> str:
    vn = b.get("venue_name") or ""
    un = b.get("unit_name") or ""
    if un:
        return f"{vn} — {un}"
    return vn or f"Площадка {b.get('venue_id', '?')}"


def _serialize_booking(b: dict) -> dict:
    return {
        "id":             b["id"],
        "venue_id":       b["venue_id"],
        "venue_unit_id":  b["venue_unit_id"],
        "activity":       b["activity"],
        "title":          b["title"],
        "status":         b["status"],
        "comment":        b["comment"],
        "tenant_id":      b["tenant_id"],
        "gz_group_id":    b["gz_group_id"],
        "tenant_name":    b["tenant_name"],
        "gz_group_name":  b["gz_group_name"],
        "gz_is_free":     b["gz_is_free"],
        "venue_name":     b.get("venue_name") or "",
        "unit_name":      b.get("unit_name") or "",
        "resource_name":  _resolve_resource_name(b),
        "starts_at":      b["starts_at"].isoformat() if b["starts_at"] else None,
        "ends_at":        b["ends_at"].isoformat()   if b["ends_at"]   else None,
    }


def _build_grid(slots, resources, bookings, day, ws):
    day_start = datetime.combine(day, ws, tzinfo=TZ)
    n_rows    = len(slots)
    n_cols    = len(resources)

    unit_to_col:  dict[int, int] = {}
    venue_to_col: dict[int, int] = {}
    for i, r in enumerate(resources):
        if r["venue_unit_id"]:
            unit_to_col[r["venue_unit_id"]] = i
        else:
            venue_to_col[r["venue_id"]] = i

    grid          = [[None] * n_cols for _ in range(n_rows)]
    booking_spans = {}

    for b in bookings:
        col = None
        if b["venue_unit_id"]:
            col = unit_to_col.get(b["venue_unit_id"])
        if col is None:
            col = venue_to_col.get(b["venue_id"])
        if col is None:
            continue

        bk_start = max(b["starts_at"], day_start)
        bk_end   = min(b["ends_at"],   day_start + timedelta(hours=24))
        if bk_end <= bk_start:
            continue

        r0 = int((bk_start - day_start).total_seconds() // (SLOT_MINUTES * 60))
        r1 = int(((bk_end  - day_start).total_seconds() - 1) // (SLOT_MINUTES * 60))
        r0 = max(0, r0)
        r1 = min(n_rows - 1, r1)

        for rr in range(r0, r1 + 1):
            grid[rr][col] = b["id"]

        display_name = (
            b["gz_group_name"] or "ГЗ"
            if b["activity"] == "GZ"
            else b["tenant_name"] or "ПД"
        )

        booking_spans[b["id"]] = {
            "col":          col,
            "row_start":    r0,
            "row_end":      r1,
            "span":         r1 - r0 + 1,
            "booking":      _serialize_booking(b),
            "display_name": display_name,
            "time_str":     f"{b['starts_at']:%H:%M}–{b['ends_at']:%H:%M}",
        }

    return grid, booking_spans


def _period_range(anchor: date, period: str) -> tuple[date, date]:
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start  = anchor.replace(day=1)
        next_m = (start.replace(year=start.year + 1, month=1)
                  if start.month == 12
                  else start.replace(month=start.month + 1))
        return start, next_m - timedelta(days=1)
    if period == "quarter":
        q       = (anchor.month - 1) // 3
        start_m = q * 3 + 1
        start   = anchor.replace(month=start_m, day=1)
        next_q  = (start.replace(year=start.year + 1, month=1)
                   if start_m == 10
                   else start.replace(month=start_m + 3))
        return start, next_q - timedelta(days=1)
    if period == "year":
        return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31)
    return anchor, anchor


def _kind_title(activity: str) -> str:
    a = (activity or "").upper()
    if a == "PD": return "ПД"
    if a == "GZ": return "ГЗ"
    return a or "—"


def _status_title(status: str) -> str:
    s = (status or "").lower()
    if s == "planned":   return "План"
    if s == "done":      return "Проведено"
    if s == "cancelled": return "Отменено"
    return s or "—"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/schedule", response_class=HTMLResponse)
def schedule_page(
    request: Request,
    org_id:         Optional[int] = Query(None),
    day:            Optional[str] = Query(None),
    show_cancelled: bool          = Query(False),
    view:           str           = Query("grid"),
    period:         str           = Query("day"),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    orgs = _load_orgs(conn, user)
    if not orgs:
        return templates.TemplateResponse("schedule.html", {
            "request":       request,
            "user":          user,
            "orgs":          [],
            "selected_org":  None,
            "error":         "Нет доступных учреждений",
            "has_analytics": False,
        })

    if org_id is None:
        org_id = orgs[0]["id"]
    selected_org = next((o for o in orgs if o["id"] == org_id), orgs[0])
    org_id = selected_org["id"]

    require_org_access(user, org_id, conn)

    try:
        selected_day = date.fromisoformat(day) if day else date.today()
    except ValueError:
        selected_day = date.today()

    ws = time(0, 0)       if selected_org["is_24h"] else selected_org["work_start"]
    we = time(23, 59, 59) if selected_org["is_24h"] else selected_org["work_end"]

    view   = view   if view   in ("grid", "list")                          else "grid"
    period = period if period in ("day", "week", "month", "quarter", "year") else "day"

    # Определяем диапазон дат для фильтрации ресурсов
    # В grid-режиме — один день; в list-режиме — выбранный период
    if view == "grid":
        filter_from = selected_day
        filter_to   = selected_day
    else:
        filter_from, filter_to = _period_range(selected_day, period)

    # Ресурсы уже отфильтрованы по доступности
    resources = _load_resources(conn, org_id, filter_from, filter_to)
    venue_ids = list({r["venue_id"] for r in resources})
    slots     = _time_slots(ws, we)

    prev_day     = selected_day - timedelta(days=1)
    next_day     = selected_day + timedelta(days=1)
    weekdays_ru  = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_weekday  = weekdays_ru[selected_day.weekday()]

    grid          = []
    spans         = {}
    list_bookings = []
    list_period_label = ""
    list_stats = {"total": 0, "pd": 0, "gz": 0, "cancelled": 0, "busy_hours": 0.0}

    if view == "grid":
        day_start = datetime.combine(selected_day, ws, tzinfo=TZ)
        day_end   = datetime.combine(selected_day, we, tzinfo=TZ)
        bookings  = _load_bookings(conn, venue_ids, day_start, day_end, show_cancelled)
        grid, spans = _build_grid(slots, resources, bookings, selected_day, ws)

    else:
        d0, d1 = filter_from, filter_to
        list_period_label = f"{d0:%d.%m.%Y} – {d1:%d.%m.%Y}"
        start_dt    = datetime.combine(d0, time(0, 0), tzinfo=TZ)
        end_dt      = datetime.combine(d1 + timedelta(days=1), time(0, 0), tzinfo=TZ)
        bookings_raw = _load_bookings(conn, venue_ids, start_dt, end_dt, show_cancelled)

        total    = len(bookings_raw)
        pd_cnt   = sum(1 for b in bookings_raw if (b["activity"] or "").upper() == "PD")
        gz_cnt   = sum(1 for b in bookings_raw if (b["activity"] or "").upper() == "GZ")
        canc     = sum(1 for b in bookings_raw if (b["status"]   or "").lower() == "cancelled")
        busy_sec = sum(
            int((b["ends_at"] - b["starts_at"]).total_seconds())
            for b in bookings_raw
            if b["starts_at"] and b["ends_at"]
        )

        list_stats = {
            "total":      total,
            "pd":         pd_cnt,
            "gz":         gz_cnt,
            "cancelled":  canc,
            "busy_hours": round(busy_sec / 3600.0, 1),
        }

        for b in bookings_raw:
            activity = (b["activity"] or "").upper()
            tenant   = (
                b["gz_group_name"] or "ГЗ"
                if activity == "GZ"
                else b["tenant_name"] or "ПД"
            )
            list_bookings.append({
                "id":            b["id"],
                "date_str":      b["starts_at"].strftime("%d.%m.%Y") if b["starts_at"] else "",
                "time_str":      (f"{b['starts_at']:%H:%M}–{b['ends_at']:%H:%M}"
                                  if b["starts_at"] and b["ends_at"] else ""),
                "tenant":        tenant,
                "title":         b["title"] or "",
                "resource_name": _resolve_resource_name(b),
                "kind":          _kind_title(b["activity"]),
                "kind_raw":      activity,
                "status":        _status_title(b["status"]),
                "status_raw":    (b["status"] or "").lower(),
                "booking":       _serialize_booking(b),
            })

    show_analytics = (
        has_permission(conn, user, "page.analytics")
        or has_permission(conn, user, "tab.analytics")
    )

    return templates.TemplateResponse("schedule.html", {
        "request":            request,
        "user":               user,
        "orgs":               orgs,
        "selected_org":       selected_org,
        "org_id":             org_id,
        "selected_day":       selected_day,
        "day_weekday":        day_weekday,
        "prev_day":           prev_day.isoformat(),
        "next_day":           next_day.isoformat(),
        "today":              date.today().isoformat(),
        "resources":          resources,
        "slots":              slots,
        "grid":               grid,
        "spans":              spans,
        "show_cancelled":     show_cancelled,
        "total_bookings":     len(spans) if view == "grid" else list_stats["total"],
        "view":               view,
        "period":             period,
        "list_bookings":      list_bookings,
        "list_period_label":  list_period_label,
        "list_stats":         list_stats,
        "has_analytics":      show_analytics,
    })
