# web/routers/load.py
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Dict, Tuple
from collections import defaultdict

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2.extras import RealDictCursor

from web.deps import get_db, get_current_user, require_org_access

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

TZ = timezone(timedelta(hours=3))


def _has_permission(conn, user_id: int, perm_code: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM app_user_permissions WHERE user_id=%s AND perm_code=%s LIMIT 1",
            (user_id, perm_code),
        )
        return cur.fetchone() is not None


def _load_orgs(conn, user: dict) -> list:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user.get("role_code") == "admin":
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


def _load_available_venue_ids(
    conn,
    venue_ids: list[int],
    week_start: date,
    week_end: date,
) -> set[int]:
    """
    Возвращает venue_id, у которых хотя бы один день недели доступен:
    - не закрыт (org_closures / venue_closures)
    - в сезоне (is_venue_in_season)
    Площадки, у которых ВСЕ 7 дней закрыты/вне сезона — исключаются.
    """
    if not venue_ids:
        return set()

    days = [week_start + timedelta(days=i) for i in range(7)]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        # org_id для каждой площадки
        cur.execute(
            "SELECT id, org_id FROM public.venues WHERE id = ANY(%s)",
            (venue_ids,),
        )
        venue_org: dict[int, int] = {row["id"]: row["org_id"] for row in cur.fetchall()}
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
                (org_ids, week_start, week_end),
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
            (venue_ids, week_start, week_end),
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


def _load_resources(conn, org_id: int, week_start: date, week_end: date) -> list:
    """
    Ресурсы учреждения, отфильтрованные по доступности на неделю.
    Площадки, закрытые или вне сезона всю неделю — не показываются.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT v.id AS venue_id, v.name AS venue_name,
                   vu.id AS venue_unit_id, vu.name AS unit_name, vu.sort_order
            FROM venues v
            LEFT JOIN venue_units vu ON vu.venue_id = v.id AND vu.is_active = true
            WHERE v.org_id = %s AND v.is_active = true
            ORDER BY v.name, vu.sort_order NULLS FIRST, vu.name
            """,
            (org_id,),
        )
        rows = cur.fetchall()

    # Сначала собираем все ресурсы (без фильтрации)
    all_resources = []
    seen_venues: set[int] = set()

    for r in rows:
        if r["venue_unit_id"]:
            all_resources.append({
                "venue_id":      r["venue_id"],
                "venue_unit_id": r["venue_unit_id"],
                "name":          f"{r['venue_name']} — {r['unit_name']}",
                "short_name":    r["unit_name"],
                "venue_name":    r["venue_name"],
            })
            seen_venues.add(r["venue_id"])
        else:
            if r["venue_id"] not in seen_venues:
                all_resources.append({
                    "venue_id":      r["venue_id"],
                    "venue_unit_id": None,
                    "name":          r["venue_name"],
                    "short_name":    r["venue_name"],
                    "venue_name":    r["venue_name"],
                })
                seen_venues.add(r["venue_id"])

    # Фильтруем по доступности на неделю
    all_venue_ids = list({r["venue_id"] for r in all_resources})
    try:
        available_ids = _load_available_venue_ids(conn, all_venue_ids, week_start, week_end)
    except Exception:
        # Fallback — показываем всё, чтобы не сломать страницу
        available_ids = set(all_venue_ids)

    return [r for r in all_resources if r["venue_id"] in available_ids]


def _week_range(anchor: date) -> Tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def _sec_between(t0: time, t1: time) -> int:
    return int(
        (
            datetime.combine(date.today(), t1)
            - datetime.combine(date.today(), t0)
        ).total_seconds()
    )


def _overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    s = max(a0, b0)
    e = min(a1, b1)
    return max(0, int((e - s).total_seconds()))


def _load_bookings(
    conn,
    org_id: int,
    start_dt: datetime,
    end_dt: datetime,
    include_cancelled: bool,
) -> list:
    cancel = "" if include_cancelled else "AND b.status <> 'cancelled'"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT b.id, b.venue_id, b.venue_unit_id, b.starts_at, b.ends_at, b.status
            FROM bookings b
            JOIN venues v ON v.id = b.venue_id
            WHERE v.org_id = %s
              AND b.starts_at < %s AND b.ends_at > %s
              {cancel}
            """,
            (org_id, end_dt, start_dt),
        )
        return cur.fetchall()


def _build_heatmap(
    resources: list,
    bookings: list,
    week_start: date,
    ws: time,
    we: time,
) -> Dict[Tuple[int, Optional[int], date], int]:
    busy = defaultdict(int)
    res_keys = {(r["venue_id"], r["venue_unit_id"]) for r in resources}

    for b in bookings:
        for i in range(7):
            d  = week_start + timedelta(days=i)
            w0 = datetime.combine(d, ws, tzinfo=TZ)
            w1 = datetime.combine(d, we, tzinfo=TZ)

            sec = _overlap_seconds(b["starts_at"], b["ends_at"], w0, w1)
            if sec <= 0:
                continue

            key = (b["venue_id"], b["venue_unit_id"])
            if b["venue_unit_id"] is not None and key in res_keys:
                busy[(b["venue_id"], b["venue_unit_id"], d)] += sec
            elif (b["venue_id"], None) in res_keys:
                busy[(b["venue_id"], None, d)] += sec

    return busy


@router.get("/load", response_class=HTMLResponse)
def load_page(
    request: Request,
    org_id: Optional[int] = Query(None),
    day: Optional[str] = Query(None),
    show_cancelled: bool = Query(False),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    orgs = _load_orgs(conn, user)

    is_admin = user.get("role_code") == "admin"
    has_analytics = (
        is_admin
        or _has_permission(conn, user["id"], "page.analytics")
        or _has_permission(conn, user["id"], "tab.analytics")
    )

    if not orgs:
        return templates.TemplateResponse(
            "load.html",
            {
                "request":      request,
                "user":         user,
                "orgs":         [],
                "selected_org": None,
                "error":        "Нет доступных учреждений",
                "has_analytics": has_analytics,
            },
        )

    if org_id is None:
        org_id = orgs[0]["id"]
    selected_org = next((o for o in orgs if o["id"] == org_id), orgs[0])
    org_id = selected_org["id"]

    require_org_access(user, org_id, conn)

    try:
        anchor = date.fromisoformat(day) if day else date.today()
    except ValueError:
        anchor = date.today()

    week_start, week_end = _week_range(anchor)
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    days        = [week_start + timedelta(days=i) for i in range(7)]
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    ws      = time(0, 0)       if selected_org["is_24h"] else selected_org["work_start"]
    we      = time(23, 59, 59) if selected_org["is_24h"] else selected_org["work_end"]
    cap_day = _sec_between(ws, we)

    # Ресурсы уже отфильтрованы по доступности на неделю
    resources = _load_resources(conn, org_id, week_start, week_end)

    start_dt = datetime.combine(week_start, time(0, 0), tzinfo=TZ)
    end_dt   = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=TZ)
    bookings = _load_bookings(conn, org_id, start_dt, end_dt, show_cancelled)

    busy = _build_heatmap(resources, bookings, week_start, ws, we)

    grid = []
    for r in resources:
        row = {"resource": r, "cells": []}
        for d in days:
            sec = busy.get((r["venue_id"], r["venue_unit_id"], d), 0)
            pct = 0.0 if cap_day <= 0 else round(100.0 * sec / cap_day, 1)
            row["cells"].append({
                "date":     d,
                "weekday":  weekdays_ru[d.weekday()],
                "busy_sec": sec,
                "pct":      pct,
                "link": (
                    f"/schedule?org_id={org_id}"
                    f"&day={d.isoformat()}"
                    f"&view=grid&period=day"
                    f"&show_cancelled={'true' if show_cancelled else 'false'}"
                ),
            })
        grid.append(row)

    return templates.TemplateResponse(
        "load.html",
        {
            "request":      request,
            "user":         user,
            "orgs":         orgs,
            "selected_org": selected_org,
            "org_id":       org_id,
            "anchor":       anchor,
            "week_start":   week_start,
            "week_end":     week_end,
            "prev_week":    prev_week,
            "next_week":    next_week,
            "days":         days,
            "weekdays_ru":  weekdays_ru,
            "resources":    resources,
            "grid":         grid,
            "show_cancelled": show_cancelled,
            "ws":           ws,
            "we":           we,
            "has_analytics": has_analytics,
        },
    )
