from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor

from web.deps import get_db, get_current_user
from web.routers.schedule import (
    _load_resources, _load_bookings, _time_slots, _build_grid, TZ, SLOT_MINUTES
)

router = APIRouter()


@router.get("/schedule/day")
def api_day_schedule(
    org_id: int = Query(...),
    day: str = Query(...),
    show_cancelled: bool = Query(False),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    """JSON-версия для подгрузки без перезагрузки страницы."""
    selected_day = date.fromisoformat(day)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT work_start, work_end, is_24h FROM sport_orgs WHERE id=%s",
            (org_id,),
        )
        org = cur.fetchone()

    ws = time(0, 0) if org["is_24h"] else org["work_start"]
    we = time(23, 59, 59) if org["is_24h"] else org["work_end"]

    resources = _load_resources(conn, org_id)
    venue_ids = list({r["venue_id"] for r in resources})
    slots = _time_slots(ws, we)

    day_start = datetime.combine(selected_day, ws, tzinfo=TZ)
    day_end = datetime.combine(selected_day, we, tzinfo=TZ)
    bookings = _load_bookings(conn, venue_ids, day_start, day_end, show_cancelled)

    grid, spans = _build_grid(slots, resources, bookings, selected_day, ws)

    return {
        "resources": resources,
        "slots": [s.strftime("%H:%M") for s in slots],
        "grid": grid,
        "spans": {
            str(k): {
                **v,
                "booking": {
                    **v["booking"],
                    "starts_at": v["booking"]["starts_at"].isoformat(),
                    "ends_at": v["booking"]["ends_at"].isoformat(),
                },
            }
            for k, v in spans.items()
        },
        "total_bookings": len(spans),
    }
