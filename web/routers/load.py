from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Dict, Tuple, List
from collections import defaultdict

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from psycopg2.extras import RealDictCursor

from web.deps import get_db, get_current_user, require_org_access

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

TZ = timezone(timedelta(hours=3))


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


def _load_resources(conn, org_id: int) -> list:
    """Те же ресурсы, что в schedule: зоны как отдельные ресурсы, иначе площадка."""
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

    resources = []
    seen = set()
    for r in rows:
        if r["venue_unit_id"]:
            resources.append({
                "venue_id": r["venue_id"],
                "venue_unit_id": r["venue_unit_id"],
                "name": f"{r['venue_name']} — {r['unit_name']}",
                "short_name": r["unit_name"],
                "venue_name": r["venue_name"],
            })
            seen.add(r["venue_id"])
        elif r["venue_id"] not in seen:
            resources.append({
                "venue_id": r["venue_id"],
                "venue_unit_id": None,
                "name": r["venue_name"],
                "short_name": r["venue_name"],
                "venue_name": r["venue_name"],
            })
            seen.add(r["venue_id"])
    return resources


def _week_range(anchor: date) -> Tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())  # Пн
    return start, start + timedelta(days=6)            # Вс


def _sec_between(t0: time, t1: time) -> int:
    return int((datetime.combine(date.today(), t1) - datetime.combine(date.today(), t0)).total_seconds())


def _overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    s = max(a0, b0)
    e = min(a1, b1)
    return max(0, int((e - s).total_seconds()))


def _load_bookings(conn, org_id: int, start_dt: datetime, end_dt: datetime, include_cancelled: bool) -> list:
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


def _build_heatmap(resources: list, bookings: list, week_start: date, ws: time, we: time) -> Dict[Tuple[int, Optional[int], date], int]:
    """
    Возвращает занятые секунды по ключу (venue_id, venue_unit_id, day).
    Логика совпадает с триггером: если бронирование с unit_id — оно относится к зоне,
    иначе к площадке целиком.
    """
    busy = defaultdict(int)

    # индекс ресурсов для быстрых проверок существования
    res_keys = {(r["venue_id"], r["venue_unit_id"]) for r in resources}

    for b in bookings:
        for i in range(7):
            d = week_start + timedelta(days=i)
            w0 = datetime.combine(d, ws, tzinfo=TZ)
            w1 = datetime.combine(d, we, tzinfo=TZ)

            sec = _overlap_seconds(b["starts_at"], b["ends_at"], w0, w1)
            if sec <= 0:
                continue

            # ключ бронирования: зона или площадка
            key = (b["venue_id"], b["venue_unit_id"])
            if b["venue_unit_id"] is not None and key in res_keys:
                busy[(b["venue_id"], b["venue_unit_id"], d)] += sec
            else:
                # если бронирование без зоны — относим к "площадке" (unit=None)
                if (b["venue_id"], None) in res_keys:
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
    if not orgs:
        return templates.TemplateResponse("load.html", {
            "request": request,
            "user": user,
            "orgs": [],
            "selected_org": None,
            "error": "Нет доступных учреждений",
        })

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
    days = [week_start + timedelta(days=i) for i in range(7)]
    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    ws = time(0, 0) if selected_org["is_24h"] else selected_org["work_start"]
    we = time(23, 59, 59) if selected_org["is_24h"] else selected_org["work_end"]
    cap_day = _sec_between(ws, we)

    resources = _load_resources(conn, org_id)

    start_dt = datetime.combine(week_start, time(0, 0), tzinfo=TZ)
    end_dt = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=TZ)
    bookings = _load_bookings(conn, org_id, start_dt, end_dt, show_cancelled)

    busy = _build_heatmap(resources, bookings, week_start, ws, we)

    # подготовим матрицу процентов
    grid = []
    for r in resources:
        row = {
            "resource": r,
            "cells": []
        }
        for d in days:
            sec = busy.get((r["venue_id"], r["venue_unit_id"], d), 0)
            pct = 0.0 if cap_day <= 0 else round(100.0 * sec / cap_day, 1)
            row["cells"].append({
                "date": d,
                "weekday": weekdays_ru[d.weekday()],
                "busy_sec": sec,
                "pct": pct,
                "link": f"/schedule?org_id={org_id}&day={d.isoformat()}&view=grid&period=day&show_cancelled={'true' if show_cancelled else 'false'}",
            })
        grid.append(row)

    return templates.TemplateResponse("load.html", {
        "request": request,
        "user": user,
        "orgs": orgs,
        "selected_org": selected_org,
        "org_id": org_id,
        "anchor": anchor,
        "week_start": week_start,
        "week_end": week_end,
        "days": days,
        "weekdays_ru": weekdays_ru,
        "resources": resources,
        "grid": grid,
        "show_cancelled": show_cancelled,
        "ws": ws,
        "we": we,
    })
