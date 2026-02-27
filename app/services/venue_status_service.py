# app/services/venue_status_service.py
from __future__ import annotations
import datetime
from app.db import get_connection  # адаптируйте под ваш модуль подключения


def has_active_org_closures(org_id: int) -> bool:
    """Есть ли активные (будущие или текущие) закрытия учреждения."""
    today = datetime.date.today()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM org_closures
                    WHERE org_id = %s AND is_active = true AND date_to >= %s
                )
                """,
                (org_id, today),
            )
            return cur.fetchone()[0]


def has_active_venue_closures(venue_id: int) -> bool:
    """Есть ли активные (будущие или текущие) закрытия площадки."""
    today = datetime.date.today()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM venue_closures
                    WHERE venue_id = %s AND is_active = true AND date_to >= %s
                )
                """,
                (venue_id, today),
            )
            return cur.fetchone()[0]


def has_venue_seasons(venue_id: int) -> bool:
    """Есть ли настроенная сезонность у площадки."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM venue_season_templates
                    WHERE venue_id = %s AND is_active = true
                    UNION ALL
                    SELECT 1 FROM venue_season_overrides
                    WHERE venue_id = %s AND is_active = true
                )
                """,
                (venue_id, venue_id),
            )
            return cur.fetchone()[0]


def get_venue_statuses(venue_ids: list[int]) -> dict[int, dict]:
    """
    Пакетный запрос статусов для списка площадок.
    Возвращает {venue_id: {'has_closures': bool, 'has_seasons': bool}}
    """
    if not venue_ids:
        return {}
    
    today = datetime.date.today()
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Закрытия площадок
            cur.execute(
                """
                SELECT DISTINCT venue_id FROM venue_closures
                WHERE venue_id = ANY(%s) AND is_active = true AND date_to >= %s
                """,
                (venue_ids, today),
            )
            closed_venue_ids = {row[0] for row in cur.fetchall()}
            
            # Сезонность (шаблоны)
            cur.execute(
                """
                SELECT DISTINCT venue_id FROM venue_season_templates
                WHERE venue_id = ANY(%s) AND is_active = true
                """,
                (venue_ids,),
            )
            seasonal_venue_ids = {row[0] for row in cur.fetchall()}
            
            # Сезонность (переопределения)
            cur.execute(
                """
                SELECT DISTINCT venue_id FROM venue_season_overrides
                WHERE venue_id = ANY(%s) AND is_active = true
                """,
                (venue_ids,),
            )
            seasonal_venue_ids |= {row[0] for row in cur.fetchall()}

    return {
        vid: {
            "has_closures": vid in closed_venue_ids,
            "has_seasons": vid in seasonal_venue_ids,
        }
        for vid in venue_ids
    }


def get_org_closure_statuses(org_ids: list[int]) -> dict[int, bool]:
    """
    Пакетный запрос: есть ли активные закрытия у учреждений.
    Возвращает {org_id: has_closures}
    """
    if not org_ids:
        return {}
    today = datetime.date.today()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT org_id FROM org_closures
                WHERE org_id = ANY(%s) AND is_active = true AND date_to >= %s
                """,
                (org_ids, today),
            )
            closed_org_ids = {row[0] for row in cur.fetchall()}
    
    return {oid: oid in closed_org_ids for oid in org_ids}
