from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import List, Iterable, Optional

import os
import tempfile

from psycopg2.extras import RealDictCursor
from psycopg2 import errors

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class Booking:
    id: int
    venue_id: int
    venue_unit_id: Optional[int]
    tenant_id: Optional[int]
    title: str
    kind: str  # 'PD' или 'GZ' (в БД это bookings.activity)
    starts_at: datetime
    ends_at: datetime
    status: str  # planned/cancelled/done
    tenant_name: str
    venue_unit_name: str


def list_bookings_for_day(
    venue_ids: Iterable[int],
    day: date,
    include_cancelled: bool = False,
) -> List[Booking]:
    venue_ids = [int(x) for x in venue_ids]
    if not venue_ids:
        return []

    day_start = datetime.combine(day, time(0, 0))
    day_end = day_start + timedelta(days=1)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT
                    b.id,
                    b.venue_id,
                    b.venue_unit_id,
                    b.tenant_id,
                    b.title,
                    b.activity AS kind,
                    b.starts_at,
                    b.ends_at,
                    b.status,
                    COALESCE(t.name, '') AS tenant_name,
                    COALESCE(vu.name, '') AS venue_unit_name
                FROM public.bookings b
                LEFT JOIN public.tenants t ON t.id = b.tenant_id
                LEFT JOIN public.venue_units vu ON vu.id = b.venue_unit_id
                WHERE b.venue_id = ANY(%s)
                  AND b.starts_at < %s
                  AND b.ends_at   > %s
            """
            params = [venue_ids, day_end, day_start]

            if not include_cancelled:
                sql += " AND b.status <> 'cancelled'"

            sql += " ORDER BY b.starts_at"

            cur.execute(sql, params)
            rows = cur.fetchall()

            return [
                Booking(
                    id=int(r["id"]),
                    venue_id=int(r["venue_id"]),
                    venue_unit_id=(int(r["venue_unit_id"]) if r["venue_unit_id"] is not None else None),
                    tenant_id=(int(r["tenant_id"]) if r["tenant_id"] is not None else None),
                    title=str(r.get("title") or ""),
                    kind=str(r.get("kind") or ""),
                    starts_at=r["starts_at"],
                    ends_at=r["ends_at"],
                    status=str(r.get("status") or "planned"),
                    tenant_name=str(r.get("tenant_name") or ""),
                    venue_unit_name=str(r.get("venue_unit_name") or ""),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def _log(msg: str) -> None:
    path = os.path.join(tempfile.gettempdir(), "booking_debug.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


def create_booking(
    *,
    venue_id: int,
    tenant_id: int | None,
    title: str,
    kind: str,
    starts_at: datetime,
    ends_at: datetime,
    venue_unit_id: int | None = None,
) -> int:
    # title НЕ обязателен: в БД title NOT NULL, поэтому храним пустую строку вместо NULL
    title = (title or "").strip()
    kind = (kind or "").strip().upper()

    _log(
        "create_booking called: "
        f"venue_id={venue_id}, venue_unit_id={venue_unit_id}, tenant_id={tenant_id}, kind={kind}, "
        f"starts_at={starts_at!r}, ends_at={ends_at!r}, title={title!r}"
    )

    if kind not in ("PD", "GZ"):
        raise ValueError("Тип занятости должен быть PD или GZ")
    if ends_at <= starts_at:
        raise ValueError("Окончание должно быть позже начала")

    conn = None
    try:
        conn = get_conn()

        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user, inet_server_addr(), inet_server_port(), now();")
            _log("db session: " + str(cur.fetchone()))
            cur.execute("show transaction_read_only;")
            _log("transaction_read_only: " + str(cur.fetchone()))

        # (не обязательно, но полезно) валидация: unit должен принадлежать venue
        if venue_unit_id is not None:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM public.venue_units WHERE id=%s AND venue_id=%s",
                    (int(venue_unit_id), int(venue_id)),
                )
                if cur.fetchone() is None:
                    raise ValueError("Выбранная часть площадки (unit) не принадлежит указанной площадке")

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.bookings(
                    venue_id, venue_unit_id, tenant_id, title, activity, starts_at, ends_at, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'planned')
                RETURNING id
                """,
                (
                    int(venue_id),
                    int(venue_unit_id) if venue_unit_id is not None else None,
                    int(tenant_id) if tenant_id is not None else None,
                    title,  # может быть ''
                    kind,
                    starts_at,
                    ends_at,
                ),
            )
            new_id = int(cur.fetchone()[0])

        conn.commit()
        _log(f"commit ok, new_id={new_id}")
        return new_id

    except Exception as e:
        if conn:
            conn.rollback()

        pgcode = getattr(e, "pgcode", None)
        _log(f"ERROR: {type(e).__name__}: {e!r}, pgcode={pgcode}")

        if isinstance(e, errors.ExclusionViolation) or pgcode == "23P01":
            raise RuntimeError("Площадка занята в выбранный интервал.") from e

        raise

    finally:
        if conn:
            put_conn(conn)


def get_booking(booking_id: int) -> Booking:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    b.id,
                    b.venue_id,
                    b.venue_unit_id,
                    b.tenant_id,
                    b.title,
                    b.activity AS kind,
                    b.starts_at,
                    b.ends_at,
                    b.status,
                    COALESCE(t.name, '') AS tenant_name,
                    COALESCE(vu.name, '') AS venue_unit_name
                FROM public.bookings b
                LEFT JOIN public.tenants t ON t.id = b.tenant_id
                LEFT JOIN public.venue_units vu ON vu.id = b.venue_unit_id
                WHERE b.id=%s
                """,
                (int(booking_id),),
            )
            r = cur.fetchone()
            if not r:
                raise ValueError("Бронирование не найдено")

            return Booking(
                id=int(r["id"]),
                venue_id=int(r["venue_id"]),
                venue_unit_id=(int(r["venue_unit_id"]) if r["venue_unit_id"] is not None else None),
                tenant_id=(int(r["tenant_id"]) if r["tenant_id"] is not None else None),
                title=str(r.get("title") or ""),
                kind=str(r.get("kind") or ""),
                starts_at=r["starts_at"],
                ends_at=r["ends_at"],
                status=str(r.get("status") or "planned"),
                tenant_name=str(r.get("tenant_name") or ""),
                venue_unit_name=str(r.get("venue_unit_name") or ""),
            )
    finally:
        if conn:
            put_conn(conn)


def update_booking(
    booking_id: int,
    *,
    tenant_id: int | None,
    title: str,
    kind: str,
    venue_unit_id: int | None,
) -> None:
    # title НЕ обязателен
    title = (title or "").strip()
    kind = (kind or "").strip().upper()

    if kind not in ("PD", "GZ"):
        raise ValueError("Тип занятости должен быть PD или GZ")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.bookings
                SET tenant_id=%s,
                    title=%s,
                    activity=%s,
                    venue_unit_id=%s
                WHERE id=%s
                """,
                (
                    int(tenant_id) if tenant_id is not None else None,
                    title,  # может быть ''
                    kind,
                    int(venue_unit_id) if venue_unit_id is not None else None,
                    int(booking_id),
                ),
            )
            if cur.rowcount != 1:
                raise ValueError("Бронирование не найдено")
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()

        pgcode = getattr(e, "pgcode", None)
        if isinstance(e, errors.ExclusionViolation) or pgcode == "23P01":
            raise RuntimeError("Площадка занята в выбранный интервал.") from e
        raise
    finally:
        if conn:
            put_conn(conn)


def cancel_booking(booking_id: int) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.bookings SET status='cancelled' WHERE id=%s",
                (int(booking_id),),
            )
            if cur.rowcount != 1:
                raise ValueError("Бронирование не найдено")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)
            
def cancel_future_bookings_like_rule(
    *,
    tenant_id: int,
    venue_unit_id: int,
    weekday: int,          # 1..7 (Mon..Sun)
    starts_at: time,
    ends_at: time,
    from_day: date,
    activity: str = "PD",
) -> int:
    """
    Эвристически отменяет будущие бронирования, которые выглядят как созданные по правилу.

    Матчинг:
      - tenant_id совпадает
      - venue_unit_id совпадает
      - activity совпадает (PD по умолчанию)
      - status <> 'cancelled'
      - starts_at::date >= from_day
      - isodow(starts_at) == weekday
      - starts_at::time == starts_at и ends_at::time == ends_at (точное совпадение времени)
    Возвращает количество отменённых строк.
    """
    activity = (activity or "PD").strip().upper()
    if activity not in ("PD", "GZ"):
        raise ValueError("activity должен быть PD или GZ")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.bookings
                SET status='cancelled'
                WHERE tenant_id = %s
                  AND venue_unit_id = %s
                  AND activity = %s::public.activity_type
                  AND status <> 'cancelled'
                  AND starts_at::date >= %s
                  AND extract(isodow from starts_at) = %s
                  AND starts_at::time = %s
                  AND ends_at::time   = %s
                """,
                (
                    int(tenant_id),
                    int(venue_unit_id),
                    activity,
                    from_day,
                    int(weekday),
                    starts_at,
                    ends_at,
                ),
            )
            affected = int(cur.rowcount)
        conn.commit()
        return affected
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)
