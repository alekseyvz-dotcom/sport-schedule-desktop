from __future__ import annotations

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from datetime import date, time, datetime, timedelta, timezone
from typing import Optional
from decimal import Decimal

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


# ─── НОВОЕ: загрузка venue_units ───

def load_venue_units(venue_id: int) -> list[dict]:
    """
    Загружает все активные зоны (venue_units) для данной площадки.
    Возвращает список dict: {id, venue_id, code, name, fraction, sort_order}
    Отсортирован по sort_order, name.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, venue_id, code, name, fraction, sort_order
                FROM venue_units
                WHERE venue_id = %s AND is_active = true
                ORDER BY sort_order, name
                """,
                (venue_id,),
            )
            return cur.fetchall()


def get_portion_options(venue_id: int) -> list[dict]:
    """
    Определяет варианты бронирования для площадки на основе venue_units.

    Возвращает список вариантов:
    [
        {"label": "1/4 поля", "fraction": 0.25, "units_needed": 1},
        {"label": "1/2 поля", "fraction": 0.50, "units_needed": 2},
        {"label": "Целое поле", "fraction": 1.00, "units_needed": 4},
    ]

    Если площадка не разбита (нет units или 1 unit с fraction=1.0) — возвращает [].
    """
    units = load_venue_units(venue_id)

    if not units:
        return []

    # Если один unit с fraction=1.0 — площадка не делится
    if len(units) == 1 and float(units[0]["fraction"]) >= 1.0:
        return []

    total_units = len(units)
    unit_fraction = float(units[0]["fraction"])  # предполагаем одинаковую дробь

    options = []

    if total_units == 4 and abs(unit_fraction - 0.25) < 0.01:
        # Площадка из 4 четвертей
        options = [
            {"label": "1/4 поля", "fraction": 0.25, "units_needed": 1, "callback": "portion:1"},
            {"label": "1/2 поля", "fraction": 0.50, "units_needed": 2, "callback": "portion:2"},
            {"label": "Целое поле", "fraction": 1.00, "units_needed": 4, "callback": "portion:4"},
        ]
    elif total_units == 2 and abs(unit_fraction - 0.5) < 0.01:
        # Площадка из 2 половин
        options = [
            {"label": "1/2 поля", "fraction": 0.50, "units_needed": 1, "callback": "portion:1"},
            {"label": "Целое поле", "fraction": 1.00, "units_needed": 2, "callback": "portion:2"},
        ]
    else:
        # Произвольное разбиение — предлагаем каждый unit отдельно + целое
        for i, u in enumerate(units):
            frac = float(u["fraction"])
            label = u["name"]
            options.append({
                "label": label,
                "fraction": frac,
                "units_needed": 1,
                "callback": f"portion:1:unit:{u['id']}",
            })
        # Целое поле
        options.append({
            "label": "Целое поле",
            "fraction": 1.0,
            "units_needed": total_units,
            "callback": f"portion:{total_units}",
        })

    return options


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
    units_needed: int = 0,
) -> list[dict]:
    """
    Вычисляет свободные слоты.

    Если units_needed > 0 — проверяем доступность по venue_units:
    слот считается свободным, если >= units_needed зон свободны в этот интервал.

    Если units_needed == 0 — старая логика (площадка целиком, без учёта unit-ов).
    """
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

    if day_end <= day_start:
        return []

    # Загружаем venue_units если нужна проверка по зонам
    all_units = []
    if units_needed > 0:
        all_units = load_venue_units(venue_id)
        if not all_units:
            # Нет зон — фоллбэк на старую логику
            units_needed = 0

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if units_needed > 0 and all_units:
                # Загружаем бронирования ПО КАЖДОМУ unit
                unit_ids = [u["id"] for u in all_units]
                cur.execute(
                    """
                    SELECT b.venue_unit_id, b.starts_at, b.ends_at
                    FROM bookings b
                    WHERE b.venue_id = %s
                      AND b.starts_at < %s AND b.ends_at > %s
                      AND b.status <> 'cancelled'
                      AND (b.venue_unit_id = ANY(%s) OR b.venue_unit_id IS NULL)
                    """,
                    (venue_id, day_end, day_start, unit_ids),
                )
                bookings = cur.fetchall()

                # Загружаем pending заявки по unit
                cur.execute(
                    """
                    SELECT br.venue_unit_id, br.desired_start, br.desired_end
                    FROM booking_requests br
                    WHERE br.venue_id = %s AND br.desired_date = %s
                      AND br.status IN ('new', 'confirmed')
                      AND (br.venue_unit_id = ANY(%s) OR br.venue_unit_id IS NULL)
                    """,
                    (venue_id, d, unit_ids),
                )
                pending = cur.fetchall()
            else:
                # Старая логика — целиком площадка
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

        if free and units_needed > 0 and all_units:
            # Считаем сколько unit-ов свободны в этом слоте
            free_unit_count = 0
            for unit in all_units:
                unit_id = unit["id"]
                unit_busy = False

                # Проверяем бронирования
                for bk in bookings:
                    # Бронирование без unit_id = занята ВСЯ площадка
                    if bk.get("venue_unit_id") is None or bk["venue_unit_id"] == unit_id:
                        if s_start < bk["ends_at"] and s_end > bk["starts_at"]:
                            unit_busy = True
                            break

                # Проверяем pending заявки
                if not unit_busy:
                    for rq in pending:
                        rq_s = datetime.combine(d, rq["desired_start"], tzinfo=TZ)
                        rq_e = datetime.combine(d, rq["desired_end"], tzinfo=TZ)
                        if rq.get("venue_unit_id") is None or rq["venue_unit_id"] == unit_id:
                            if s_start < rq_e and s_end > rq_s:
                                unit_busy = True
                                break

                if not unit_busy:
                    free_unit_count += 1

            # Слот свободен только если достаточно свободных зон
            if free_unit_count < units_needed:
                free = False

        elif free and units_needed == 0:
            # Старая логика — без unit-ов
            for bk in bookings:
                if s_start < bk["ends_at"] and s_end > bk["starts_at"]:
                    free = False
                    break

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


def find_free_unit_ids(
    venue_id: int,
    org_id: int,
    d: date,
    start_time: time,
    end_time: time,
    units_needed: int,
) -> list[int]:
    """
    Находит конкретные свободные venue_unit_id-ы для данного временного интервала.
    Возвращает список из units_needed свободных unit_id.
    Если свободных не хватает — возвращает пустой список.
    """
    all_units = load_venue_units(venue_id)
    if not all_units:
        return []

    s_start = datetime.combine(d, start_time, tzinfo=TZ)
    s_end = datetime.combine(d, end_time, tzinfo=TZ)
    day_start = s_start
    day_end = s_end

    unit_ids = [u["id"] for u in all_units]

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT b.venue_unit_id, b.starts_at, b.ends_at
                FROM bookings b
                WHERE b.venue_id = %s
                  AND b.starts_at < %s AND b.ends_at > %s
                  AND b.status <> 'cancelled'
                  AND (b.venue_unit_id = ANY(%s) OR b.venue_unit_id IS NULL)
                """,
                (venue_id, day_end, day_start, unit_ids),
            )
            bookings = cur.fetchall()

            cur.execute(
                """
                SELECT br.venue_unit_id, br.desired_start, br.desired_end
                FROM booking_requests br
                WHERE br.venue_id = %s AND br.desired_date = %s
                  AND br.status IN ('new', 'confirmed')
                  AND (br.venue_unit_id = ANY(%s) OR br.venue_unit_id IS NULL)
                """,
                (venue_id, d, unit_ids),
            )
            pending = cur.fetchall()

    free_ids = []
    for unit in all_units:
        unit_id = unit["id"]
        unit_busy = False

        for bk in bookings:
            if bk.get("venue_unit_id") is None or bk["venue_unit_id"] == unit_id:
                if s_start < bk["ends_at"] and s_end > bk["starts_at"]:
                    unit_busy = True
                    break

        if not unit_busy:
            for rq in pending:
                rq_s = datetime.combine(d, rq["desired_start"], tzinfo=TZ)
                rq_e = datetime.combine(d, rq["desired_end"], tzinfo=TZ)
                if rq.get("venue_unit_id") is None or rq["venue_unit_id"] == unit_id:
                    if s_start < rq_e and s_end > rq_s:
                        unit_busy = True
                        break

        if not unit_busy:
            free_ids.append(unit_id)

        if len(free_ids) >= units_needed:
            break

    return free_ids if len(free_ids) >= units_needed else []


def save_request(data: dict) -> int:
    """
    Сохраняет заявку. Если передан venue_unit_ids (список) — создаёт
    отдельную заявку для каждого unit. Возвращает id первой заявки.
    """
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Europe/Moscow'")

        venue_unit_ids = data.get("venue_unit_ids")
        if not venue_unit_ids:
            # Одна заявка (старое поведение)
            venue_unit_ids = [data.get("venue_unit_id")]

        first_id = None
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for unit_id in venue_unit_ids:
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
                        unit_id,
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
                if first_id is None:
                    first_id = req_id

        conn.commit()
        log.info("Saved booking request(s), first id=#%s, units=%s", first_id, venue_unit_ids)
        return first_id
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
