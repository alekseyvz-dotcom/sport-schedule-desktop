from __future__ import annotations

import uuid
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

    today = date.today()
    last_day = today + timedelta(days=settings.MAX_DAYS_AHEAD)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT v.id AS venue_id,
                       v.name AS venue_name
                FROM venues v
                WHERE v.org_id = %s
                  AND v.is_active = true

                  -- площадка не закрыта на весь период
                  AND NOT EXISTS (
                      SELECT 1
                      FROM venue_closures vc
                      WHERE vc.venue_id = v.id
                        AND vc.is_active = true
                        AND vc.date_from <= %s
                        AND vc.date_to >= %s
                  )

                  -- есть хотя бы один день сезона в доступном диапазоне
                  AND EXISTS (
                      SELECT 1
                      FROM generate_series(%s::date, %s::date, interval '1 day') d(day)
                      WHERE public.is_venue_in_season(v.id, d.day)
                  )

                ORDER BY v.name
                """,
                (
                    org_id,
                    today,
                    last_day,
                    today,
                    last_day,
                ),
            )
            rows = cur.fetchall()

    resources = []
    for r in rows:
        resources.append({
            "venue_id": r["venue_id"],
            "venue_unit_id": None,
            "name": r["venue_name"],
        })

    return resources


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

    - 4 unit-а (fraction=0.25): 1/4, 1/2, Целое
    - 2 unit-а (fraction=0.50): 1/2, Целое
    - 1 unit или нет unit-ов: [] (шаг пропускается)
    """
    units = load_venue_units(venue_id)

    if not units:
        return []

    # Один unit с fraction=1.0 — площадка не делится
    if len(units) == 1 and float(units[0]["fraction"]) >= 1.0:
        return []

    total_units = len(units)

    if total_units == 4:
        return [
            {"label": "1/4 поля", "fraction": 0.25, "units_needed": 1, "callback": "portion:1"},
            {"label": "1/2 поля", "fraction": 0.50, "units_needed": 2, "callback": "portion:2"},
            {"label": "Целое поле", "fraction": 1.00, "units_needed": 4, "callback": "portion:4"},
        ]
    elif total_units == 2:
        return [
            {"label": "1/2 поля", "fraction": 0.50, "units_needed": 1, "callback": "portion:1"},
            {"label": "Целое поле", "fraction": 1.00, "units_needed": 2, "callback": "portion:2"},
        ]
    elif total_units == 3:
        return [
            {"label": "1/3 поля", "fraction": 0.33, "units_needed": 1, "callback": "portion:1"},
            {"label": "2/3 поля", "fraction": 0.67, "units_needed": 2, "callback": "portion:2"},
            {"label": "Целое поле", "fraction": 1.00, "units_needed": 3, "callback": "portion:3"},
        ]
    else:
        # Любое другое количество — предлагаем только целое
        # (или можно пропустить шаг)
        return []


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


import uuid  # ← добавить в imports вверху файла

# ... остальные imports без изменений ...


def save_request(data: dict) -> int:
    """
    Сохраняет заявку. Если передан venue_unit_ids (список) — создаёт
    отдельную заявку для каждого unit с общим group_id.
    Возвращает id первой заявки.
    """
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'Europe/Moscow'")

        venue_unit_ids = data.get("venue_unit_ids")

        # Определяем group_id если бронируем несколько unit-ов
        group_id = None
        if venue_unit_ids and len(venue_unit_ids) > 1:
            group_id = str(uuid.uuid4())

        if not venue_unit_ids:
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
                         telegram_user_id, telegram_chat_id, message,
                         group_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                        group_id,
                    ),
                )
                req_id = cur.fetchone()["id"]
                if first_id is None:
                    first_id = req_id

        conn.commit()
        log.info(
            "Saved booking request(s), first id=#%s, units=%s, group=%s",
            first_id, venue_unit_ids, group_id,
        )
        return first_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_grouped_requests(request_id: int) -> list[dict]:
    """
    Возвращает все заявки из той же группы (group_id).
    Если group_id is NULL — возвращает только саму заявку.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Сначала получаем group_id этой заявки
            cur.execute(
                "SELECT group_id FROM booking_requests WHERE id = %s",
                (request_id,),
            )
            row = cur.fetchone()
            if not row:
                return []

            group_id = row["group_id"]

            if group_id is None:
                # Одиночная заявка
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
                result = cur.fetchone()
                return [result] if result else []
            else:
                # Групповая заявка
                cur.execute(
                    """
                    SELECT br.*, v.name AS venue_name,
                           vu.name AS unit_name, o.name AS org_name
                    FROM booking_requests br
                    JOIN venues v ON v.id = br.venue_id
                    LEFT JOIN venue_units vu ON vu.id = br.venue_unit_id
                    JOIN sport_orgs o ON o.id = br.org_id
                    WHERE br.group_id = %s
                    ORDER BY br.id
                    """,
                    (group_id,),
                )
                return cur.fetchall()


def update_group_status(
    request_id: int, status: str, staff_comment: str = None
) -> list[dict]:
    """
    Обновляет статус заявки и всех связанных заявок (по group_id).
    Возвращает список обновлённых заявок.
    """
    now = datetime.now(TZ)
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Получаем group_id
            cur.execute(
                "SELECT group_id FROM booking_requests WHERE id = %s",
                (request_id,),
            )
            row = cur.fetchone()
            if not row:
                return []

            group_id = row["group_id"]

            if group_id is None:
                # Одиночная заявка
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
                updated = cur.fetchone()
                conn.commit()
                return [updated] if updated else []
            else:
                # Все заявки группы
                cur.execute(
                    """
                    UPDATE booking_requests
                    SET status=%s, staff_comment=%s,
                        processed_at=%s, updated_at=%s
                    WHERE group_id=%s AND status='new'
                    RETURNING *
                    """,
                    (status, staff_comment, now, now, group_id),
                )
                updated = cur.fetchall()
                conn.commit()
                return updated

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_request_portion_info(request_id: int) -> dict:
    """
    Получает информацию о части площадки для заявки.
    Возвращает dict с полями:
      - venue_name, org_name
      - unit_names: список названий забронированных зон
      - total_units: общее кол-во зон площадки
      - units_booked: кол-во забронированных зон
      - portion_label: человекочитаемый лейбл ("1/4 поля", "1/2 поля", "Целое поле")
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Получаем основную заявку
            cur.execute(
                """
                SELECT br.venue_id, br.group_id, v.name AS venue_name, o.name AS org_name
                FROM booking_requests br
                JOIN venues v ON v.id = br.venue_id
                JOIN sport_orgs o ON o.id = br.org_id
                WHERE br.id = %s
                """,
                (request_id,),
            )
            req = cur.fetchone()
            if not req:
                return {}

            venue_id = req["venue_id"]
            group_id = req["group_id"]

            # Получаем все unit-ы площадки
            cur.execute(
                """
                SELECT id, name FROM venue_units
                WHERE venue_id = %s AND is_active = true
                ORDER BY sort_order, name
                """,
                (venue_id,),
            )
            all_units = cur.fetchall()
            total_units = len(all_units)

            # Получаем забронированные unit-ы
            if group_id:
                cur.execute(
                    """
                    SELECT DISTINCT vu.name
                    FROM booking_requests br
                    JOIN venue_units vu ON vu.id = br.venue_unit_id
                    WHERE br.group_id = %s
                    ORDER BY vu.name
                    """,
                    (group_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT vu.name
                    FROM booking_requests br
                    JOIN venue_units vu ON vu.id = br.venue_unit_id
                    WHERE br.id = %s
                    """,
                    (request_id,),
                )
            booked_units = cur.fetchall()
            unit_names = [u["name"] for u in booked_units]
            units_booked = len(unit_names)

    # Определяем лейбл
    if total_units == 0 or units_booked == 0:
        portion_label = ""
    elif units_booked >= total_units:
        portion_label = "Целое поле"
    else:
        fraction = units_booked / total_units
        if abs(fraction - 0.25) < 0.01:
            portion_label = "1/4 поля"
        elif abs(fraction - 0.5) < 0.01:
            portion_label = "1/2 поля"
        elif abs(fraction - 0.75) < 0.01:
            portion_label = "3/4 поля"
        else:
            portion_label = f"{units_booked}/{total_units} поля"

    return {
        "venue_name": req["venue_name"],
        "org_name": req["org_name"],
        "unit_names": unit_names,
        "total_units": total_units,
        "units_booked": units_booked,
        "portion_label": portion_label,
    }

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

def get_venue_prices(venue_id: int) -> dict:
    """
    Возвращает все цены площадки как dict.
    Ключи: price_q_60, price_q_90, price_h_60, price_h_90, price_f_60, price_f_90
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT price_q_60, price_q_90,
                       price_h_60, price_h_90,
                       price_f_60, price_f_90
                FROM public.venue_prices
                WHERE venue_id = %s AND is_active = true
                """,
                (venue_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else {}


def format_price_list(venue_id: int, total_units: int) -> str:
    """
    Формирует текстовый прайс-лист для показа при выборе зоны.
    Возвращает строку или "" если цен нет.
    """
    prices = get_venue_prices(venue_id)
    if not prices:
        return ""

    lines = []

    # 1/4 поля — только если 4 зоны
    if total_units == 4:
        p60 = prices.get("price_q_60")
        p90 = prices.get("price_q_90")
        if p60 or p90:
            parts = []
            if p60:
                parts.append(f"60 мин — {int(p60)} ₽")
            if p90:
                parts.append(f"90 мин — {int(p90)} ₽")
            lines.append(f"  • 1/4 поля: {' | '.join(parts)}")

    # 1/2 поля — если 2 или 4 зоны
    if total_units in (2, 4):
        p60 = prices.get("price_h_60")
        p90 = prices.get("price_h_90")
        if p60 or p90:
            parts = []
            if p60:
                parts.append(f"60 мин — {int(p60)} ₽")
            if p90:
                parts.append(f"90 мин — {int(p90)} ₽")
            lines.append(f"  • 1/2 поля: {' | '.join(parts)}")

    # Целое поле — всегда
    p60 = prices.get("price_f_60")
    p90 = prices.get("price_f_90")
    if p60 or p90:
        parts = []
        if p60:
            parts.append(f"60 мин — {int(p60)} ₽")
        if p90:
            parts.append(f"90 мин — {int(p90)} ₽")
        lines.append(f"  • Целое поле: {' | '.join(parts)}")

    if not lines:
        return ""

    return "💰 <b>Стоимость аренды:</b>\n" + "\n".join(lines)


def compute_booking_price(
    venue_id: int,
    units_needed: int,
    total_units: int,
    duration_minutes: int,
) -> Optional[Decimal]:
    """
    Вычисляет цену конкретного бронирования.
    Возвращает Decimal или None если цена не задана.
    """
    prices = get_venue_prices(venue_id)
    if not prices:
        return None

    # Определяем часть
    if total_units == 0 or units_needed >= total_units:
        portion = "f"
    else:
        fraction = units_needed / total_units
        if abs(fraction - 0.25) < 0.01:
            portion = "q"
        elif abs(fraction - 0.5) < 0.01:
            portion = "h"
        else:
            portion = "f"

    # Определяем длительность
    if duration_minutes <= 60:
        dur = "60"
    elif duration_minutes <= 90:
        dur = "90"
    else:
        # 120 мин = 2 × цена за 60
        price_60 = prices.get(f"price_{portion}_60")
        if price_60 is not None:
            return Decimal(str(price_60)) * 2
        return None

    val = prices.get(f"price_{portion}_{dur}")
    return Decimal(str(val)) if val is not None else None
