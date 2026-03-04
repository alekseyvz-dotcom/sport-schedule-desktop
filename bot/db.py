from __future__ import annotations

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from datetime import date, time, datetime, timedelta, timezone
from typing import Optional

from bot.config import settings

log = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=3))
SLOT = settings.SLOT_MINUTES


@contextmanager
def get_conn():
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Europe/Moscow'")
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def load_orgs() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, address, work_start, work_end, is_24h "
                "FROM sport_orgs WHERE is_active = true ORDER BY name"
            )
            return cur.fetchall()


def get_org(org_id: int) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, address, work_start, work_end, is_24h "
                "FROM sport_orgs WHERE id = %s",
                (org_id,),
            )
            return cur.fetchone()


def load_resources(org_id: int) -> list[dict]:
    """
    Загружает только площадки (venues), без venue_units.
    Фильтрует закрытые площадки (venue_closures на сегодня и далее).
    """
    today = date.today()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT v.id   AS venue_id,
                       v.name AS venue_name
                FROM venues v
                WHERE v.org_id = %s
                  AND v.is_active = true
                  -- исключаем площадки, закрытые бессрочно (date_to далеко в будущем)
                  AND NOT EXISTS (
                      SELECT 1 FROM venue_closures vc
                      WHERE vc.venue_id = v.id
                        AND vc.is_active = true
                        AND vc.date_from <= %s
                        AND vc.date_to >= %s
                  )
                ORDER BY v.name
                """,
                (org_id, today, today),
            )
            rows = cur.fetchall()

    resources = []
    for r in rows:
        resources.append({
            "venue_id":      r["venue_id"],
            "venue_unit_id": None,
            "name":          r["venue_name"],
        })
    return resources


def is_venue_available(venue_id: int, org_id: int, d: date) -> bool:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT 1 FROM org_closures "
                "WHERE org_id=%s AND is_active=true AND date_from<=%s AND date_to>=%s LIMIT 1",
                (org_id, d, d),
            )
            if cur.fetchone():
                return False

            cur.execute(
                "SELECT 1 FROM venue_closures "
                "WHERE venue_id=%s AND is_active=true AND date_from<=%s AND date_to>=%s LIMIT 1",
                (venue_id, d, d),
            )
            if cur.fetchone():
                return False

            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM venue_season_templates
                    WHERE venue_id=%s AND is_active=true
                    UNION ALL
                    SELECT 1 FROM venue_season_overrides
                    WHERE venue_id=%s AND is_active=true
                )
                """,
                (venue_id, venue_id),
            )
            if cur.fetchone()["exists"]:
                cur.execute(
                    "SELECT public.is_venue_in_season(%s, %s) AS ok",
                    (venue_id, d),
                )
                if not cur.fetchone()["ok"]:
                    return False
    return True


def compute_free_slots(
    venue_id: int,
    venue_unit_id: Optional[int],
    org_id: int,
    d: date,
) -> list[dict]:
    org = get_org(org_id)
    if not org:
        return []

    if org["is_24h"]:
        ws = time(0, 0)
        we = time(23, 59, 59)
    else:
        ws = org["work_start"]
        we = org["work_end"]

    day_start = datetime.combine(d, ws, tzinfo=TZ)
    day_end = datetime.combine(d, we, tzinfo=TZ)

    # Защита: если work_end <= work_start, не генерируем слоты через полночь
    if day_end <= day_start:
        return []

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Берём все бронирования на эту площадку (любой unit)
            cur.execute(
                """
                SELECT b.starts_at, b.ends_at
                FROM bookings b
                WHERE b.venue_id = %s
                  AND b.starts_at < %s AND b.ends_at > %s
                  AND b.status <> 'cancelled'
                """,
                (venue_id, day_end, day_start),
            )
            bookings = cur.fetchall()

            # Берём заявки на эту площадку (любой unit)
            cur.execute(
                """
                SELECT desired_start, desired_end
                FROM booking_requests
                WHERE venue_id = %s AND desired_date = %s
                  AND status IN ('new', 'confirmed')
                """,
                (venue_id, d),
            )
            pending = cur.fetchall()

    now = datetime.now(TZ)
    slots = []
    cur_dt = day_start

    while cur_dt + timedelta(minutes=SLOT) <= day_end:
        s_start = cur_dt
        s_end = cur_dt + timedelta(minutes=SLOT)
        free = True

        # Прошедшее время — не свободно
        if s_start < now:
            free = False

        # Проверка пересечений с бронированиями
        if free:
            for bk in bookings:
                bk_start = bk["ends_at"] if isinstance(bk["ends_at"], datetime) else bk["ends_at"]
                bk_end = bk["starts_at"] if isinstance(bk["starts_at"], datetime) else bk["starts_at"]
                if s_start < bk["ends_at"] and s_end > bk["starts_at"]:
                    free = False
                    break

        # Проверка пересечений с pending заявками
        if free:
            for rq in pending:
                rq_s = datetime.combine(d, rq["desired_start"], tzinfo=TZ)
                rq_e = datetime.combine(d, rq["desired_end"], tzinfo=TZ)
                if s_start < rq_e and s_end > rq_s:
                    free = False
                    break

        slots.append({
            "start": s_start.time(),
            "end":   s_end.time(),
            "free":  free,
        })
        cur_dt = s_end

    return slots


def save_request(data: dict) -> int:
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Europe/Moscow'")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO booking_requests
                    (org_id, venue_id, venue_unit_id,
                     desired_date, desired_start, desired_end,
                     contact_name, contact_phone, contact_email,
                     telegram_user_id, telegram_chat_id, message)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    data["org_id"], data["venue_id"],
                    data.get("venue_unit_id"),
                    data["desired_date"],
                    data["desired_start"], data["desired_end"],
                    data["contact_name"],
                    data.get("contact_phone"),
                    data.get("contact_email"),
                    data.get("telegram_user_id"),
                    data.get("telegram_chat_id"),
                    data.get("message"),
                ),
            )
            req_id = cur.fetchone()["id"]
        conn.commit()
        log.info("Saved booking request #%s", req_id)
        return req_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_staff_chat_ids(org_id: int) -> list[int]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT chat_id FROM org_staff_telegram "
                "WHERE org_id = %s AND is_active = true",
                (org_id,),
            )
            return [row["chat_id"] for row in cur.fetchall()]


def update_request_status(
    request_id: int, status: str, staff_comment: str = None
) -> Optional[dict]:
    now = datetime.now(TZ)
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE booking_requests
                SET status=%s, staff_comment=%s,
                    processed_at=%s, updated_at=%s
                WHERE id=%s
                RETURNING *
                """,
                (status, staff_comment, now, now, request_id),
            )
            row = cur.fetchone()
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_request_by_id(request_id: int) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT br.*, v.name AS venue_name,
                       vu.name AS unit_name, o.name AS org_name
                FROM booking_requests br
                JOIN venues v ON v.id = br.venue_id
                LEFT JOIN venue_units vu ON vu.id = br.venue_unit_id
                JOIN sport_orgs o ON o.id = br.org_id
                WHERE br.id = %s
                """,
                (request_id,),
            )
            return cur.fetchone()


def get_user_requests(telegram_user_id: int, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT br.id, br.desired_date, br.desired_start,
                       br.desired_end, br.status,
                       v.name AS venue_name, vu.name AS unit_name,
                       o.name AS org_name, br.staff_comment
                FROM booking_requests br
                JOIN venues v ON v.id = br.venue_id
                LEFT JOIN venue_units vu ON vu.id = br.venue_unit_id
                JOIN sport_orgs o ON o.id = br.org_id
                WHERE br.telegram_user_id = %s
                ORDER BY br.created_at DESC
                LIMIT %s
                """,
                (telegram_user_id, limit),
            )
            return cur.fetchall()
