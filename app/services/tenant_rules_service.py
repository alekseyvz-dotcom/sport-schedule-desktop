from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, datetime, timedelta, timezone
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.services.bookings_service import create_booking


@dataclass(frozen=True)
class TenantRule:
    id: int
    tenant_id: int
    venue_unit_id: int
    weekday: int          # 1..7 (Mon..Sun)
    starts_at: time
    ends_at: time
    valid_from: date
    valid_to: date
    title: str
    is_active: bool


def list_rules_for_tenant(tenant_id: int, include_inactive: bool = False) -> List[TenantRule]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT
                    id, tenant_id, venue_unit_id, weekday,
                    starts_at, ends_at, valid_from, valid_to,
                    title, is_active
                FROM public.tenant_recurring_rules
                WHERE tenant_id = %(tenant_id)s
            """
            params = {"tenant_id": int(tenant_id)}
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY is_active DESC, valid_from, weekday, starts_at"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                TenantRule(
                    id=int(r["id"]),
                    tenant_id=int(r["tenant_id"]),
                    venue_unit_id=int(r["venue_unit_id"]),
                    weekday=int(r["weekday"]),
                    starts_at=r["starts_at"],
                    ends_at=r["ends_at"],
                    valid_from=r["valid_from"],
                    valid_to=r["valid_to"],
                    title=str(r["title"] or ""),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_rule(
    *,
    tenant_id: int,
    venue_unit_id: int,
    weekday: int,
    starts_at: time,
    ends_at: time,
    valid_from: date,
    valid_to: date,
    title: str = "",
) -> int:
    if not (1 <= int(weekday) <= 7):
        raise ValueError("weekday должен быть от 1 до 7")
    if ends_at <= starts_at:
        raise ValueError("Время окончания должно быть больше времени начала")
    if valid_to < valid_from:
        raise ValueError("valid_to не может быть раньше valid_from")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.tenant_recurring_rules(
                    tenant_id, venue_unit_id, weekday,
                    starts_at, ends_at, valid_from, valid_to,
                    title, is_active
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true)
                RETURNING id
                """,
                (
                    int(tenant_id), int(venue_unit_id), int(weekday),
                    starts_at, ends_at, valid_from, valid_to,
                    (title or "").strip(),
                ),
            )
            rid = int(cur.fetchone()[0])
        conn.commit()
        return rid
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def set_rule_active(rule_id: int, is_active: bool) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.tenant_recurring_rules SET is_active=%s WHERE id=%s",
                    (bool(is_active), int(rule_id)),
                )
    finally:
        if conn:
            put_conn(conn)


def _iter_rule_dates(valid_from: date, valid_to: date, weekday: int):
    # weekday: 1..7 (Mon..Sun). Python date.weekday(): Mon=0..Sun=6
    target = int(weekday) - 1
    d = valid_from
    while d <= valid_to:
        if d.weekday() == target:
            yield d
        d += timedelta(days=1)


def generate_bookings_for_rule(
    *,
    rule: TenantRule,
    venue_id: int,
    tz: timezone,
) -> int:
    """
    Генерирует PD-брони по правилу.
    Возвращает количество успешно созданных броней.
    Если есть пересечения, create_booking выбросит исключение (и вы покажете его пользователю).
    """
    created = 0
    for d in _iter_rule_dates(rule.valid_from, rule.valid_to, rule.weekday):
        starts_dt = datetime.combine(d, rule.starts_at, tzinfo=tz)
        ends_dt = datetime.combine(d, rule.ends_at, tzinfo=tz)

        create_booking(
            venue_id=int(venue_id),
            venue_unit_id=int(rule.venue_unit_id),
            tenant_id=int(rule.tenant_id),
            title=rule.title or "Аренда по договору",
            kind="PD",
            starts_at=starts_dt,
            ends_at=ends_dt,
        )
        created += 1

    return created
