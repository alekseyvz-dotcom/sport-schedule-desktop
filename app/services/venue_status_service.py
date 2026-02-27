# app/services/venue_status_service.py
from __future__ import annotations

import datetime
from typing import Optional

from app.db import get_conn, put_conn


def get_venue_statuses(venue_ids: list[int]) -> dict[int, dict]:
    """
    Пакетный запрос статусов для списка площадок.
    Возвращает {venue_id: {'has_closures': bool, 'has_seasons': bool}}

    has_closures = True если есть активные текущие/будущие закрытия
                   площадки ИЛИ её учреждения.
    has_seasons  = True если настроена сезонность (шаблоны или переопределения).
    """
    if not venue_ids:
        return {}

    today = datetime.date.today()
    ids   = list(venue_ids)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:

            # org_id для каждой площадки (нужен для проверки закрытий учреждения)
            cur.execute(
                "SELECT id, org_id FROM public.venues WHERE id = ANY(%s)",
                (ids,),
            )
            venue_org: dict[int, int] = {row[0]: row[1] for row in cur.fetchall()}
            org_ids = list(set(venue_org.values()))

            # --- Закрытия учреждений (текущие и будущие) ---
            org_closed_ids: set[int] = set()
            if org_ids:
                cur.execute(
                    """
                    SELECT DISTINCT org_id
                    FROM public.org_closures
                    WHERE org_id = ANY(%s)
                      AND is_active = true
                      AND date_to >= %s
                    """,
                    (org_ids, today),
                )
                org_closed_ids = {row[0] for row in cur.fetchall()}

            # --- Закрытия самих площадок (текущие и будущие) ---
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
            venue_closed_ids = {row[0] for row in cur.fetchall()}

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

    result = {}
    for vid in venue_ids:
        org_id = venue_org.get(vid)
        # Площадка считается закрытой если закрыта она сама ИЛИ её учреждение
        has_closures = (
            vid in venue_closed_ids
            or (org_id is not None and org_id in org_closed_ids)
        )
        result[vid] = {
            "has_closures": has_closures,
            "has_seasons":  vid in seasonal_venue_ids,
        }

    return result


def get_org_closure_statuses(org_ids: list[int]) -> dict[int, bool]:
    """
    Пакетный запрос: есть ли активные (текущие/будущие) закрытия у учреждений.
    Возвращает {org_id: has_closures}
    """
    if not org_ids:
        return {}

    today = datetime.date.today()
    ids   = list(org_ids)

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


def get_available_venue_ids_for_week(
    venue_ids: list[int],
    week_start: datetime.date,
    week_end: datetime.date,
) -> set[int]:
    """
    Возвращает venue_id, у которых хотя бы один день в диапазоне
    [week_start, week_end] является доступным:
      - не закрыт (org_closures / venue_closures)
      - в сезоне (is_venue_in_season)

    Площадки, у которых ВСЕ дни диапазона закрыты/вне сезона — исключаются.
    """
    if not venue_ids:
        return set()

    ids  = list(venue_ids)
    days = []
    d    = week_start
    while d <= week_end:
        days.append(d)
        d += datetime.timedelta(days=1)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:

            # org_id для каждой площадки
            cur.execute(
                "SELECT id, org_id FROM public.venues WHERE id = ANY(%s)",
                (ids,),
            )
            venue_org: dict[int, int] = {row[0]: row[1] for row in cur.fetchall()}
            org_ids = list(set(venue_org.values()))

            # Закрытия учреждений в диапазоне
            org_closed_ranges: dict[int, list[tuple]] = {}
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
                for org_id, df, dt_ in cur.fetchall():
                    org_closed_ranges.setdefault(org_id, []).append((df, dt_))

            # Закрытия площадок в диапазоне
            venue_closed_ranges: dict[int, list[tuple]] = {}
            cur.execute(
                """
                SELECT venue_id, date_from, date_to
                FROM public.venue_closures
                WHERE venue_id = ANY(%s)
                  AND is_active = true
                  AND date_to >= %s AND date_from <= %s
                """,
                (ids, week_start, week_end),
            )
            for vid, df, dt_ in cur.fetchall():
                venue_closed_ranges.setdefault(vid, []).append((df, dt_))

            # Площадки с сезонными настройками
            cur.execute(
                """
                SELECT DISTINCT venue_id FROM public.venue_season_templates
                WHERE venue_id = ANY(%s) AND is_active = true
                UNION
                SELECT DISTINCT venue_id FROM public.venue_season_overrides
                WHERE venue_id = ANY(%s) AND is_active = true
                """,
                (ids, ids),
            )
            seasonal_ids = {row[0] for row in cur.fetchall()}

            # Пакетная проверка сезонности через БД-функцию
            seasonal_list = [vid for vid in ids if vid in seasonal_ids]
            season_ok: dict[tuple[int, datetime.date], bool] = {}
            if seasonal_list:
                cur.execute(
                    """
                    SELECT v_id, d, public.is_venue_in_season(v_id, d)
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
                for vid, d, ok in cur.fetchall():
                    season_ok[(int(vid), d)] = bool(ok)

    finally:
        if conn:
            put_conn(conn)

    # Для каждой площадки ищем хотя бы один доступный день
    available: set[int] = set()

    for vid in venue_ids:
        org_id = venue_org.get(vid)

        for d in days:
            # 1. Закрытие учреждения
            org_blocked = any(
                df <= d <= dt_
                for df, dt_ in org_closed_ranges.get(org_id or -1, [])
            )
            if org_blocked:
                continue

            # 2. Закрытие площадки
            venue_blocked = any(
                df <= d <= dt_
                for df, dt_ in venue_closed_ranges.get(vid, [])
            )
            if venue_blocked:
                continue

            # 3. Сезонность (только если настроена)
            if vid in seasonal_ids:
                if not season_ok.get((vid, d), False):
                    continue

            # Нашли доступный день — площадка включается
            available.add(vid)
            break

    return available


# ---------------------------------------------------------------------------
# Одиночные хелперы
# ---------------------------------------------------------------------------

def has_active_org_closures(org_id: int) -> bool:
    """Есть ли активные (текущие/будущие) закрытия учреждения."""
    return get_org_closure_statuses([org_id]).get(org_id, False)


def has_active_venue_closures(venue_id: int) -> bool:
    """Есть ли активные (текущие/будущие) закрытия площадки или её учреждения."""
    return get_venue_statuses([venue_id]).get(venue_id, {}).get("has_closures", False)


def has_venue_seasons(venue_id: int) -> bool:
    """Есть ли настроенная сезонность у площадки."""
    return get_venue_statuses([venue_id]).get(venue_id, {}).get("has_seasons", False)
