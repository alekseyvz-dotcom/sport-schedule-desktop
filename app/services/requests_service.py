# app/services/requests_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, datetime
from typing import Literal, Optional

from app.db import get_conn, put_conn


RequestStatus = Literal["new", "confirmed", "rejected", "cancelled"]


@dataclass(frozen=True)
class BookingRequest:
    id: int
    org_id: int
    org_name: str
    venue_id: int
    venue_name: str
    venue_unit_id: Optional[int]
    desired_date: date
    desired_start: time
    desired_end: time
    status: RequestStatus
    contact_name: str
    contact_phone: Optional[str]
    contact_email: Optional[str]
    telegram_user_id: Optional[int]
    telegram_chat_id: Optional[int]
    message: Optional[str]
    staff_comment: Optional[str]
    processed_by: Optional[int]
    processed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


def list_requests(
    *,
    user_id: int,
    role_code: str | None,
    org_id: int | None = None,
    status: RequestStatus | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 2000,
) -> list[BookingRequest]:
    q = """
        SELECT
            r.id,
            r.org_id,
            o.name AS org_name,
            r.venue_id,
            v.name AS venue_name,
            r.venue_unit_id,
            r.desired_date,
            r.desired_start,
            r.desired_end,
            r.status,
            r.contact_name,
            r.contact_phone,
            r.contact_email,
            r.telegram_user_id,
            r.telegram_chat_id,
            r.message,
            r.staff_comment,
            r.processed_by,
            r.processed_at,
            r.created_at,
            r.updated_at
        FROM public.booking_requests r
        JOIN public.sport_orgs o ON o.id = r.org_id
        JOIN public.venues v     ON v.id = r.venue_id
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
        s = f"%{search.strip()}%"
        q += """
            AND (
                r.contact_name ILIKE %s
                OR r.contact_phone ILIKE %s
                OR r.contact_email ILIKE %s
                OR v.name ILIKE %s
            )
        """
        params.extend([s, s, s, s])

    q += " ORDER BY r.created_at DESC LIMIT %s"
    params.append(int(limit))

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()

        out: list[BookingRequest] = []
        for row in rows:
            (
                rid, roid, org_name, vid, venue_name, venue_unit_id,
                desired_date, desired_start, desired_end,
                rstatus, contact_name, contact_phone, contact_email,
                telegram_user_id, telegram_chat_id,
                message, staff_comment, processed_by, processed_at,
                created_at, updated_at
            ) = row

            out.append(BookingRequest(
                id=rid,
                org_id=roid,
                org_name=org_name,
                venue_id=vid,
                venue_name=venue_name,
                venue_unit_id=venue_unit_id,
                desired_date=desired_date,
                desired_start=desired_start,
                desired_end=desired_end,
                status=rstatus,
                contact_name=contact_name or "",
                contact_phone=contact_phone,
                contact_email=contact_email,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                message=message,
                staff_comment=staff_comment,
                processed_by=processed_by,
                processed_at=processed_at,
                created_at=created_at,
                updated_at=updated_at,
            ))
        return out
    finally:
        put_conn(conn)


def set_request_status(
    *,
    user_id: int,
    role_code: str | None,
    request_id: int,
    status: RequestStatus,
    staff_comment: str | None = None,
) -> None:
    """
    Меняет статус заявки.
    Заполняет processed_by/processed_at, обновляет updated_at.
    staff_comment перезаписываем, если передан (в т.ч. пустой строкой).
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if staff_comment is None:
                cur.execute(
                    """
                    UPDATE public.booking_requests
                       SET status = %s,
                           processed_by = %s,
                           processed_at = now(),
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (status, user_id, request_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE public.booking_requests
                       SET status = %s,
                           staff_comment = %s,
                           processed_by = %s,
                           processed_at = now(),
                           updated_at = now()
                     WHERE id = %s
                    """,
                    (status, staff_comment, user_id, request_id),
                )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
