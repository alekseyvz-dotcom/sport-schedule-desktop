# app/services/requests_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, datetime
from typing import Iterable, Literal, Optional

from app.services.db import get_conn  # <-- поправь импорт под ваш проект


RequestStatus = Literal["new", "confirmed", "rejected", "cancelled"]


@dataclass
class BookingRequest:
    id: int
    org_id: int
    org_name: str
    venue_id: int
    venue_name: str
    desired_date: date
    desired_start: time
    desired_end: time
    status: RequestStatus
    contact_name: str
    contact_phone: Optional[str]
    message: Optional[str]
    staff_comment: Optional[str]
    created_at: datetime
    telegram_user_id: Optional[int]


def list_requests(
    *,
    user_id: int,
    role_code: str | None,
    org_id: int | None = None,
    status: RequestStatus | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 500,
) -> list[BookingRequest]:
    """
    Список заявок (для админки/десктопа).
    Фильтры: org_id, status, поиск (ФИО/тел/площадка), диапазон дат.
    """
    q = """
        SELECT
            r.id,
            r.org_id,
            o.name  AS org_name,
            r.venue_id,
            v.name  AS venue_name,
            r.desired_date,
            r.desired_start,
            r.desired_end,
            r.status,
            r.contact_name,
            r.contact_phone,
            r.message,
            r.staff_comment,
            r.created_at,
            r.telegram_user_id
        FROM sport_requests r
        JOIN sport_orgs o   ON o.id = r.org_id
        JOIN sport_venues v ON v.id = r.venue_id
        WHERE 1=1
    """
    params: list[object] = []

    if org_id is not None:
        q += " AND r.org_id = %s"
        params.append(org_id)

    if status is not None:
        q += " AND r.status = %s"
        params.append(status)

    if date_from is not None:
        q += " AND r.desired_date >= %s"
        params.append(date_from)

    if date_to is not None:
        q += " AND r.desired_date <= %s"
        params.append(date_to)

    if search:
        q += " AND (r.contact_name ILIKE %s OR r.contact_phone ILIKE %s OR v.name ILIKE %s)"
        s = f"%{search.strip()}%"
        params.extend([s, s, s])

    q += " ORDER BY r.created_at DESC"
    q += " LIMIT %s"
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()

    out: list[BookingRequest] = []
    for row in rows:
        # cursor без RealDictCursor: row — tuple.
        # Если у вас dict cursor — адаптируй ниже (row["id"], ...)
        (
            rid, roid, org_name, vid, venue_name,
            desired_date, desired_start, desired_end,
            rstatus, contact_name, contact_phone,
            message, staff_comment, created_at, telegram_user_id
        ) = row

        out.append(BookingRequest(
            id=rid,
            org_id=roid,
            org_name=org_name,
            venue_id=vid,
            venue_name=venue_name,
            desired_date=desired_date,
            desired_start=desired_start,
            desired_end=desired_end,
            status=rstatus,
            contact_name=contact_name,
            contact_phone=contact_phone,
            message=message,
            staff_comment=staff_comment,
            created_at=created_at,
            telegram_user_id=telegram_user_id,
        ))
    return out


def set_request_status(
    *,
    user_id: int,
    role_code: str | None,
    request_id: int,
    status: RequestStatus,
    staff_comment: str | None = None,
) -> None:
    """
    Обновить статус заявки (confirmed/rejected/cancelled).
    staff_comment сохраняем, если передан.
    """
    q = "UPDATE sport_requests SET status = %s, staff_comment = COALESCE(%s, staff_comment) WHERE id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (status, staff_comment, request_id))
        conn.commit()
