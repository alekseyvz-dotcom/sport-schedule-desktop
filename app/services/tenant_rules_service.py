from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, datetime, timedelta, timezone
from typing import List, Tuple

from psycopg2.extras import RealDictCursor
from psycopg2 import errors as pg_errors

from app.db import get_conn, put_conn
from app.services.bookings_service import create_booking, create_pd_booking


TENANT_RULES_EDIT_ROLES = {"admin"}  # при необходимости расширьте


def _norm_role(role_code: str) -> str:
    return (role_code or "").strip().lower()


def _require_rules_view(*, user_id: int, role_code: str) -> None:
    if not user_id:
        raise PermissionError("Недостаточно прав: просмотр правил запрещён")


def _require_rules_edit(*, user_id: int, role_code: str) -> None:
    _require_rules_view(user_id=user_id, role_code=role_code)
    if _norm_role(role_code) not in TENANT_RULES_EDIT_ROLES:
        raise PermissionError("Недостаточно прав: редактирование правил запрещено")


@dataclass(frozen=True)
class TenantRule:
    id: int
    tenant_id: int
    venue_unit_id: int
    weekday: int  # 1..7 (Mon..Sun)
    starts_at: time
    ends_at: time
    valid_from: date
    valid_to: date
    title: str
    is_active: bool


@dataclass
class GenerateReport:
    created: int
    skipped: int
    errors: List[str]


def list_rules_for_tenant(
    *,
    user_id: int,
    role_code: str,
    tenant_id: int,
    include_inactive: bool = False,
) -> List[TenantRule]:
    _require_rules_view(user_id=user_id, role_code=role_code)

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
    user_id: int,
    role_code: str,
    tenant_id: int,
    venue_unit_id: int,
    weekday: int,
    starts_at: time,
    ends_at: time,
    valid_from: date,
    valid_to: date,
    title: str = "",
) -> int:
    _require_rules_edit(user_id=user_id, role_code=role_code)

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
                    int(tenant_id),
                    int(venue_unit_id),
                    int(weekday),
                    starts_at,
                    ends_at,
                    valid_from,
                    valid_to,
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


def set_rule_active(*, user_id: int, role_code: str, rule_id: int, is_active: bool) -> None:
    _require_rules_edit(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.tenant_recurring_rules SET is_active=%s WHERE id=%s",
                    (bool(is_active), int(rule_id)),
                )
                if cur.rowcount != 1:
                    raise ValueError("Правило не найдено")
    finally:
        if conn:
            put_conn(conn)


def delete_rule(*, user_id: int, role_code: str, rule_id: int) -> None:
    _require_rules_edit(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.tenant_recurring_rules WHERE id=%s", (int(rule_id),))
                if cur.rowcount != 1:
                    raise ValueError("Правило не найдено")
    finally:
        if conn:
            put_conn(conn)


def _iter_rule_dates(valid_from: date, valid_to: date, weekday: int):
    target = int(weekday) - 1  # Python: Mon=0..Sun=6
    d = valid_from
    while d <= valid_to:
        if d.weekday() == target:
            yield d
        d += timedelta(days=1)


def get_venue_id_by_unit(venue_unit_id: int) -> int:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT venue_id FROM public.venue_units WHERE id=%s", (int(venue_unit_id),))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Не найдена зона venue_unit_id={venue_unit_id}")
            return int(row["venue_id"])
    finally:
        if conn:
            put_conn(conn)


def _get_tenant_name_and_kind(tenant_id: int) -> Tuple[str, str]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT name, tenant_kind FROM public.tenants WHERE id=%s", (int(tenant_id),))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Контрагент tenant_id={tenant_id} не найден")
            name = str(row.get("name") or "").strip()
            kind = str(row.get("tenant_kind") or "legal").strip()
            return name, kind
    finally:
        if conn:
            put_conn(conn)


def _default_booking_title(*, tenant_name: str, tenant_kind: str) -> str:
    base = tenant_name.strip() or "Контрагент"
    suffix = "Оферта" if tenant_kind == "person" else "Аренда по договору"
    return f"{base} — {suffix}"


def generate_bookings_for_rule_soft(*, rule: TenantRule, venue_id: int, tz: timezone) -> GenerateReport:
    created = 0
    skipped = 0
    errors: List[str] = []

    tenant_name, tenant_kind = _get_tenant_name_and_kind(rule.tenant_id)
    fallback_title = _default_booking_title(tenant_name=tenant_name, tenant_kind=tenant_kind)

    for d in _iter_rule_dates(rule.valid_from, rule.valid_to, rule.weekday):
        starts_dt = datetime.combine(d, rule.starts_at, tzinfo=tz)
        ends_dt = datetime.combine(d, rule.ends_at, tzinfo=tz)
        try:
            create_pd_booking(
                venue_id=int(venue_id),
                venue_unit_id=int(rule.venue_unit_id),
                tenant_id=int(rule.tenant_id),
                title=(rule.title or "").strip() or fallback_title,
                starts_at=starts_dt,
                ends_at=ends_dt,
            )
            created += 1
        except Exception as e:
            skipped += 1

            msg = str(e)
            # только это считаем "нормальным" пропуском
            if "Площадка занята" in msg:
                continue

            # всё остальное — это реальные ошибки, их надо видеть
            errors.append(
                f"{d} {rule.starts_at}-{rule.ends_at} unit={rule.venue_unit_id} venue={venue_id}: {type(e).__name__}: {e}"
            )
            pgcode = getattr(e, "pgcode", None)
            msg = str(e)

            # занято/пересечение — это нормальный skip, не ошибка
            if pgcode == "P0001" and "Пересечение по времени" in msg:
                continue

            errors.append(f"{d} {rule.starts_at}-{rule.ends_at}: {e}")

    return GenerateReport(created=created, skipped=skipped, errors=errors)


def generate_bookings_for_tenant(*, user_id: int, role_code: str, tenant_id: int, tz: timezone) -> GenerateReport:
    # генерация создаёт брони => это операция изменения
    _require_rules_edit(user_id=user_id, role_code=role_code)

    rules = list_rules_for_tenant(user_id=user_id, role_code=role_code, tenant_id=int(tenant_id), include_inactive=False)

    total_created = 0
    total_skipped = 0
    errors: List[str] = []

    for rule in rules:
        venue_id = get_venue_id_by_unit(rule.venue_unit_id)
        rep = generate_bookings_for_rule_soft(rule=rule, venue_id=venue_id, tz=tz)
        total_created += rep.created
        total_skipped += rep.skipped
        errors.extend(rep.errors)

    return GenerateReport(created=total_created, skipped=total_skipped, errors=errors)
