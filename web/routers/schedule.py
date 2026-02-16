from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2.extras import RealDictCursor

from web.deps import get_db, get_current_user, require_org_access

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

TZ = timezone(timedelta(hours=3))
SLOT_MINUTES = 30


def _load_orgs(conn, user: dict) -> list:
    """Учреждения, доступные пользователю."""
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


def _load_resources(conn, org_id: int) -> list:
    """Ресурсы (колонки сетки): площадка + зона."""
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

    resources = []
    seen = set()
    for r in rows:
        if r["venue_unit_id"]:
            resources.append({
                "venue_id": r["venue_id"],
                "venue_unit_id": r["venue_unit_id"],
                "name": f"{r['venue_name']} — {r['unit_name']}",
                "short_name": r["unit_name"],
            })
            seen.add(r["venue_id"])
        elif r["venue_id"] not in seen:
            resources.append({
                "venue_id": r["venue_id"],
                "venue_unit_id": None,
                "name": r["venue_name"],
                "short_name": r["venue_name"],
            })
            seen.add(r["venue_id"])
    return resources


def _load_bookings(conn, venue_ids: list, start: datetime, end: datetime,
                   include_cancelled: bool = False) -> list:
    cancel_filter = "" if include_cancelled else "AND b.status <> 'cancelled'"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT b.id, b.venue_id, b.venue_unit_id,
                   b.activity, b.title, b.starts_at, b.ends_at,
                   b.status, b.comment,
                   b.tenant_id, b.gz_group_id,
                   t.name AS tenant_name,
                   CONCAT(c.full_name, ' / ', g.group_year) AS gz_group_name,
                   COALESCE(g.is_free, false) AS gz_is_free
            FROM bookings b
            LEFT JOIN tenants t ON t.id = b.tenant_id
            LEFT JOIN gz_groups g ON g.id = b.gz_group_id
            LEFT JOIN gz_coaches c ON c.id = g.coach_id
            WHERE b.venue_id = ANY(%s)
              AND b.starts_at < %s AND b.ends_at > %s
              {cancel_filter}
            ORDER BY b.starts_at
            """,
            (venue_ids, end, start),
        )
        return cur.fetchall()


def _time_slots(ws: time, we: time) -> list:
    slots = []
    cur = datetime.combine(date.today(), ws)
    end = datetime.combine(date.today(), we)
    while cur < end:
        slots.append(cur.time())
        cur += timedelta(minutes=SLOT_MINUTES)
    return slots


def _build_grid(slots, resources, bookings, day, ws):
    """
    Строит матрицу grid[row][col] = booking | None
    + вычисляет span (row_start, row_end) для каждого booking.
    """
    day_start = datetime.combine(day, ws, tzinfo=TZ)
    n_rows = len(slots)
    n_cols = len(resources)

    # Маппинг ресурс -> колонка
    unit_to_col = {}
    venue_to_col = {}
    for i, r in enumerate(resources):
        if r["venue_unit_id"]:
            unit_to_col[r["venue_unit_id"]] = i
        else:
            venue_to_col[r["venue_id"]] = i

    grid = [[None] * n_cols for _ in range(n_rows)]
    booking_spans = {}  # booking_id -> {col, row_start, row_end, booking}

    for b in bookings:
        col = None
        if b["venue_unit_id"]:
            col = unit_to_col.get(b["venue_unit_id"])
        if col is None:
            col = venue_to_col.get(b["venue_id"])
        if col is None:
            continue

        bk_start = max(b["starts_at"], day_start)
        bk_end = min(b["ends_at"], day_start + timedelta(hours=24))
        if bk_end <= bk_start:
            continue

        r0 = int((bk_start - day_start).total_seconds() // (SLOT_MINUTES * 60))
        r1 = int(((bk_end - day_start).total_seconds() - 1) // (SLOT_MINUTES * 60))
        r0 = max(0, r0)
        r1 = min(n_rows - 1, r1)

        for rr in range(r0, r1 + 1):
            grid[rr][col] = b["id"]

        # Имя для отображения
        if b["activity"] == "GZ":
            display_name = b["gz_group_name"] or "ГЗ"
        else:
            display_name = b["tenant_name"] or "ПД"

        booking_spans[b["id"]] = {
            "col": col,
            "row_start": r0,
            "row_end": r1,
            "span": r1 - r0 + 1,
            "booking": b,
            "display_name": display_name,
            "time_str": f"{b['starts_at']:%H:%M}–{b['ends_at']:%H:%M}",
        }

    return grid, booking_spans


@router.get("/schedule", response_class=HTMLResponse)
def schedule_page(
    request: Request,
    org_id: Optional[int] = Query(None),
    day: Optional[str] = Query(None),
    show_cancelled: bool = Query(False),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    orgs = _load_orgs(conn, user)
    if not orgs:
        return templates.TemplateResponse("schedule.html", {
            "request": request,
            "user": user,
            "orgs": [],
            "selected_org": None,
            "error": "Нет доступных учреждений",
        })

    # Выбранное учреждение
    if org_id is None:
        org_id = orgs[0]["id"]
    selected_org = next((o for o in orgs if o["id"] == org_id), orgs[0])
    org_id = selected_org["id"]

    require_org_access(user, org_id, conn)

    # Дата
    try:
        selected_day = date.fromisoformat(day) if day else date.today()
    except ValueError:
        selected_day = date.today()

    # Рабочие часы
    ws = time(0, 0) if selected_org["is_24h"] else selected_org["work_start"]
    we = time(23, 59, 59) if selected_org["is_24h"] else selected_org["work_end"]

    # Данные
    resources = _load_resources(conn, org_id)
    venue_ids = list({r["venue_id"] for r in resources})
    slots = _time_slots(ws, we)

    day_start = datetime.combine(selected_day, ws, tzinfo=TZ)
    day_end = datetime.combine(selected_day, we, tzinfo=TZ)
    bookings = _load_bookings(conn, venue_ids, day_start, day_end, show_cancelled)

    grid, spans = _build_grid(slots, resources, bookings, selected_day, ws)

    # Навигация по дням
    prev_day = selected_day - timedelta(days=1)
    next_day = selected_day + timedelta(days=1)

    # Дни недели для заголовка
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_weekday = weekdays_ru[selected_day.weekday()]

    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "user": user,
        "orgs": orgs,
        "selected_org": selected_org,
        "org_id": org_id,
        "selected_day": selected_day,
        "day_weekday": day_weekday,
        "prev_day": prev_day.isoformat(),
        "next_day": next_day.isoformat(),
        "today": date.today().isoformat(),
        "resources": resources,
        "slots": slots,
        "grid": grid,
        "spans": spans,
        "show_cancelled": show_cancelled,
        "total_bookings": len(spans),
    })
