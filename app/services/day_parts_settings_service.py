from __future__ import annotations

from typing import Optional

from psycopg2.extras import RealDictCursor

from app.core.day_parts_settings import DayPartsSettings
from app.db import get_conn, put_conn


def get_default_day_parts_settings() -> DayPartsSettings:
    return DayPartsSettings()


def _row_to_settings(row: dict | None) -> DayPartsSettings:
    if not row:
        return get_default_day_parts_settings()

    return DayPartsSettings(
        morning_start=row["morning_start"].strftime("%H:%M"),
        morning_end=row["morning_end"].strftime("%H:%M"),
        day_start=row["day_start"].strftime("%H:%M"),
        day_end=row["day_end"].strftime("%H:%M"),
        evening_start=row["evening_start"].strftime("%H:%M"),
        evening_end=row["evening_end"].strftime("%H:%M"),
    )


def get_day_parts_settings(org_id: Optional[int] = None) -> DayPartsSettings:
    """
    Возвращает настройки интервалов:
    1) для конкретного учреждения (если есть),
    2) иначе глобальные,
    3) иначе дефолт из кода.
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if org_id is not None:
                cur.execute(
                    """
                    SELECT
                        org_id,
                        morning_start,
                        morning_end,
                        day_start,
                        day_end,
                        evening_start,
                        evening_end
                    FROM public.analytics_day_parts
                    WHERE is_active = true
                      AND (org_id = %(org_id)s OR org_id IS NULL)
                    ORDER BY
                        CASE WHEN org_id = %(org_id)s THEN 0 ELSE 1 END,
                        id DESC
                    LIMIT 1
                    """,
                    {"org_id": int(org_id)},
                )
                row = cur.fetchone()
                return _row_to_settings(row)

            cur.execute(
                """
                SELECT
                    org_id,
                    morning_start,
                    morning_end,
                    day_start,
                    day_end,
                    evening_start,
                    evening_end
                FROM public.analytics_day_parts
                WHERE is_active = true
                  AND org_id IS NULL
                ORDER BY id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return _row_to_settings(row)
    finally:
        if conn:
            put_conn(conn)


def save_day_parts_settings(settings: DayPartsSettings, org_id: Optional[int] = None) -> None:
    """
    Сохраняет настройки:
    - org_id=None  -> глобальные
    - org_id=...   -> для конкретного учреждения

    Реализация:
    1) деактивируем старую активную запись нужного уровня
    2) вставляем новую активную запись
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            if org_id is None:
                cur.execute(
                    """
                    UPDATE public.analytics_day_parts
                    SET is_active = false,
                        updated_at = now()
                    WHERE org_id IS NULL
                      AND is_active = true
                    """
                )
            else:
                cur.execute(
                    """
                    UPDATE public.analytics_day_parts
                    SET is_active = false,
                        updated_at = now()
                    WHERE org_id = %(org_id)s
                      AND is_active = true
                    """,
                    {"org_id": int(org_id)},
                )

            cur.execute(
                """
                INSERT INTO public.analytics_day_parts (
                    org_id,
                    morning_start,
                    morning_end,
                    day_start,
                    day_end,
                    evening_start,
                    evening_end,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (
                    %(org_id)s,
                    %(morning_start)s::time,
                    %(morning_end)s::time,
                    %(day_start)s::time,
                    %(day_end)s::time,
                    %(evening_start)s::time,
                    %(evening_end)s::time,
                    true,
                    now(),
                    now()
                )
                """,
                {
                    "org_id": int(org_id) if org_id is not None else None,
                    "morning_start": settings.morning_start,
                    "morning_end": settings.morning_end,
                    "day_start": settings.day_start,
                    "day_end": settings.day_end,
                    "evening_start": settings.evening_start,
                    "evening_end": settings.evening_end,
                },
            )

        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)
