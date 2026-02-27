# app/services/venue_status_service.py
from __future__ import annotations

import datetime

from app.db import get_conn, put_conn


def get_venue_statuses(venue_ids: list[int]) -> dict[int, dict]:
    """
    Пакетный запрос статусов для списка площадок.
    Возвращает {venue_id: {'has_closures': bool, 'has_seasons': bool}}
    """
    if not venue_ids:
        return {}

    today = datetime.date.today()
    # psycopg2 принимает list[int] как массив через ANY
    ids = list(venue_ids)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:

            # --- Закрытия площадок (текущие и будущие) ---
            cur.execute(
                """
                SELECT DISTINCT venue_id
                FROM public.venue_closures
                WHERE venue_id = ANY(%s)
                  AND is_active = true
                  AND date_to >= %s
                """,
                (ids, today),
            )
            closed_venue_ids = {row[0] for row in cur.fetchall()}

            # --- Сезонность: шаблоны ---
            cur.execute(
                """
                SELECT DISTINCT venue_id
                FROM public.venue_season_templates
                WHERE venue_id = ANY(%s)
                  AND is_active = true
                """,
                (ids,),
            )
            seasonal_venue_ids = {row[0] for row in cur.fetchall()}

            # --- Сезонность: переопределения по годам ---
            cur.execute(
                """
                SELECT DISTINCT venue_id
                FROM public.venue_season_overrides
                WHERE venue_id = ANY(%s)
                  AND is_active = true
                """,
                (ids,),
            )
            seasonal_venue_ids |= {row[0] for row in cur.fetchall()}

    finally:
        if conn:
            put_conn(conn)

    return {
        vid: {
            "has_closures": vid in closed_venue_ids,
            "has_seasons":  vid in seasonal_venue_ids,
        }
        for vid in venue_ids
    }


def get_org_closure_statuses(org_ids: list[int]) -> dict[int, bool]:
    """
    Пакетный запрос: есть ли активные (текущие/будущие) закрытия у учреждений.
    Возвращает {org_id: has_closures}
    """
    if not org_ids:
        return {}

    today = datetime.date.today()
    ids = list(org_ids)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT org_id
                FROM public.org_closures
                WHERE org_id = ANY(%s)
                  AND is_active = true
                  AND date_to >= %s
                """,
                (ids, today),
            )
            closed_org_ids = {row[0] for row in cur.fetchall()}
    finally:
        if conn:
            put_conn(conn)

    return {oid: oid in closed_org_ids for oid in org_ids}


def has_active_org_closures(org_id: int) -> bool:
    """Есть ли активные (текущие/будущие) закрытия учреждения."""
    result = get_org_closure_statuses([org_id])
    return result.get(org_id, False)


def has_active_venue_closures(venue_id: int) -> bool:
    """Есть ли активные (текущие/будущие) закрытия площадки."""
    result = get_venue_statuses([venue_id])
    return result.get(venue_id, {}).get("has_closures", False)


def has_venue_seasons(venue_id: int) -> bool:
    """Есть ли настроенная сезонность у площадки."""
    result = get_venue_statuses([venue_id])
    return result.get(venue_id, {}).get("has_seasons", False)
