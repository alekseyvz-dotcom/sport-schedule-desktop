from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import List, Iterable

from psycopg2.extras import RealDictCursor
from psycopg2 import errors

from app.db import get_conn, put_conn


@dataclass(frozen=True)
class Booking:
    id: int
    venue_id: int
    tenant_id: int | None
    title: str
    kind: str          # 'PD' или 'GZ' (в БД это bookings.activity)
    starts_at: datetime
    ends_at: datetime
    status: str        # planned/cancelled/done
    tenant_name: str


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
                    b.tenant_id,
                    b.title,
                    b.activity AS kind,
                    b.starts_at,
                    b.ends_at,
                    b.status,
                    COALESCE(t.name, '') AS tenant_name
                FROM public.bookings b
                LEFT JOIN public.tenants t ON t.id = b.tenant_id
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
                    tenant_id=(int(r["tenant_id"]) if r["tenant_id"] is not None else None),
                    title=str(r.get("title") or ""),
                    kind=str(r.get("kind") or ""),
                    starts_at=r["starts_at"],
                    ends_at=r["ends_at"],
                    status=str(r.get("status") or "planned"),
                    tenant_name=str(r.get("tenant_name") or ""),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def _log(msg: str) -> None:
    with open("booking_debug.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def create_booking(
    venue_id: int,
    tenant_id: int | None,
    title: str,
    kind: str,
    starts_at: datetime,
    ends_at: datetime,
) -> int:
    title = (title or "").strip()
    kind = (kind or "").strip().upper()

    _log(f"create_booking called: venue_id={venue_id}, tenant_id={tenant_id}, kind={kind}, "
         f"starts_at={starts_at!r}, ends_at={ends_at!r}, title={title!r}")

    if kind not in ("PD", "GZ"):
        raise ValueError("Тип занятости должен быть PD или GZ")
    if not title:
        raise ValueError("Название бронирования не может быть пустым")
    if ends_at <= starts_at:
        raise ValueError("Окончание должно быть позже начала")

    conn = None
    try:
        conn = get_conn()

        # ЛОГ: куда подключились (чтобы исключить "не та база")
        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user, inet_server_addr(), inet_server_port(), now();")
            _log("db session: " + str(cur.fetchone()))
            cur.execute("show transaction_read_only;")
            _log("transaction_read_only: " + str(cur.fetchone()))

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.bookings(venue_id, tenant_id, title, activity, starts_at, ends_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'planned')
                RETURNING id
                """,
                (
                    int(venue_id),
                    int(tenant_id) if tenant_id is not None else None,
                    title,
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

        # нормальное сообщение для пересечения
        if isinstance(e, errors.ExclusionViolation) or pgcode == "23P01":
            raise RuntimeError("Площадка занята в выбранный интервал.") from e

        raise

    finally:
        if conn:
            put_conn(conn)

