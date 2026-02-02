from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from psycopg2.extras import RealDictCursor
from psycopg2 import errors

from app.db import get_conn, put_conn
from app.services.bookings_service import create_booking


@dataclass(frozen=True)
class GzRule:
    id: int
    gz_group_id: int
    venue_unit_id: int
    weekday: int          # 0..6 (Mon..Sun) как в вашем tenant_rules
    starts_at: time
    ends_at: time
    valid_from: date
    valid_to: Optional[date]
    title: Optional[str]
    is_active: bool


@dataclass(frozen=True)
class GenerateReport:
    created: int
    skipped: int
    errors: List[str]


def _venue_id_by_unit(conn, venue_unit_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT venue_id FROM public.venue_units WHERE id=%s", (int(venue_unit_id),))
        r = cur.fetchone()
        if not r:
            raise ValueError("Зона/часть площадки не найдена (venue_unit_id).")
        return int(r[0])


def list_rules(gz_group_id: int, include_inactive: bool = False) -> List[GzRule]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT id, gz_group_id, venue_unit_id, weekday, starts_at, ends_at,
                       valid_from, valid_to, title, is_active
                FROM public.gz_group_rules
                WHERE gz_group_id = %s
            """
            params = [int(gz_group_id)]
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY weekday, starts_at"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                GzRule(
                    id=int(r["id"]),
                    gz_group_id=int(r["gz_group_id"]),
                    venue_unit_id=int(r["venue_unit_id"]),
                    weekday=int(r["weekday"]),
                    starts_at=r["starts_at"],
                    ends_at=r["ends_at"],
                    valid_from=r["valid_from"],
                    valid_to=r.get("valid_to"),
                    title=r.get("title"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_rule(
    *,
    gz_group_id: int,
    venue_unit_id: int,
    weekday: int,
    starts_at: time,
    ends_at: time,
    valid_from: date,
    valid_to: Optional[date],
    title: str = "",
) -> int:
    if ends_at <= starts_at:
        raise ValueError("Окончание должно быть позже начала")

    conn = None
    try:
        conn = get_conn()
        # venue_id нам нужен только чтобы валидировать unit и использовать в генерации через create_booking
        _ = _venue_id_by_unit(conn, int(venue_unit_id))

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.gz_group_rules(
                    gz_group_id, venue_unit_id, weekday,
                    starts_at, ends_at, valid_from, valid_to,
                    title, is_active
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true)
                RETURNING id
                """,
                (
                    int(gz_group_id),
                    int(venue_unit_id),
                    int(weekday),
                    starts_at,
                    ends_at,
                    valid_from,
                    valid_to,
                    (title or "").strip() or None,
                ),
            )
            new_id = int(cur.fetchone()[0])

        conn.commit()
        return new_id

    except Exception as e:
        if conn:
            conn.rollback()

        pgcode = getattr(e, "pgcode", None)
        # 23P01 = exclusion_violation (наш запрет пересечений у тренера)
        if isinstance(e, errors.ExclusionViolation) or pgcode == "23P01":
            raise RuntimeError("Пересечение правил: у этого тренера уже есть занятие в это время (по ГЗ).") from e

        raise
    finally:
        if conn:
            put_conn(conn)


def set_rule_active(rule_id: int, is_active: bool) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.gz_group_rules SET is_active=%s WHERE id=%s",
                (bool(is_active), int(rule_id)),
            )
            if cur.rowcount != 1:
                raise ValueError("Правило не найдено")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def generate_bookings_for_gz_group(gz_group_id: int, *, tz: timezone) -> GenerateReport:
    rules = list_rules(gz_group_id, include_inactive=False)
    if not rules:
        return GenerateReport(created=0, skipped=0, errors=[])

    d0 = min(r.valid_from for r in rules)
    d1 = max((r.valid_to or r.valid_from) for r in rules)

    created = 0
    skipped = 0
    errors_list: List[str] = []

    conn = None
    try:
        conn = get_conn()

        cur_day = d0
        while cur_day <= d1:
            wd = cur_day.weekday()
            for r in rules:
                if r.weekday != wd:
                    continue
                if cur_day < r.valid_from:
                    continue
                if r.valid_to and cur_day > r.valid_to:
                    continue

                venue_id = _venue_id_by_unit(conn, int(r.venue_unit_id))
                starts_dt = datetime.combine(cur_day, r.starts_at, tzinfo=tz)
                ends_dt = datetime.combine(cur_day, r.ends_at, tzinfo=tz)

                try:
                    create_booking(
                        venue_id=int(venue_id),
                        venue_unit_id=int(r.venue_unit_id),
                        tenant_id=None,
                        title=str(r.title or ""),
                        kind="GZ",
                        starts_at=starts_dt,
                        ends_at=ends_dt,
                    )
                    created += 1
                except Exception as e:
                    skipped += 1
                    errors_list.append(str(e))

            cur_day += timedelta(days=1)

        return GenerateReport(created=created, skipped=skipped, errors=errors_list)

    finally:
        if conn:
            put_conn(conn)
