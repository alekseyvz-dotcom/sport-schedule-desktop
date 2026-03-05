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
    unit_name: Optional[str]
    group_id: Optional[str]
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
    # вычисляемые поля для UI
    portion_label: str = ""
    group_unit_names: str = ""


def _compute_portion_label(units_booked: int, total_units: int) -> str:
    """Человекочитаемый лейбл части площадки."""
    if total_units == 0 or units_booked == 0:
        return ""
    if units_booked >= total_units:
        return "Целое поле"
    fraction = units_booked / total_units
    if abs(fraction - 0.25) < 0.01:
        return "1/4 поля"
    elif abs(fraction - 0.5) < 0.01:
        return "1/2 поля"
    elif abs(fraction - 0.75) < 0.01:
        return "3/4 поля"
    elif abs(fraction - 0.33) < 0.05:
        return "1/3 поля"
    elif abs(fraction - 0.67) < 0.05:
        return "2/3 поля"
    return f"{units_booked}/{total_units} поля"


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
            vu.name AS unit_name,
            r.group_id,
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
        LEFT JOIN public.venue_units vu ON vu.id = r.venue_unit_id
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
                OR vu.name ILIKE %s
            )
        """
        params.extend([s, s, s, s, s])

    q += " ORDER BY r.created_at DESC LIMIT %s"
    params.append(int(limit))

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()

        # Собираем все group_id для обогащения данных
        group_ids = set()
        for row in rows:
            gid = row[7]  # group_id
            if gid:
                group_ids.add(gid)

        # Для каждого group_id собираем unit_names и считаем units_booked
        group_info: dict[str, dict] = {}
        if group_ids:
            placeholders = ",".join(["%s"] * len(group_ids))
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        br.group_id,
                        array_agg(DISTINCT vu2.name ORDER BY vu2.name) AS unit_names,
                        COUNT(DISTINCT br.venue_unit_id) AS units_booked,
                        (
                            SELECT COUNT(*)
                            FROM venue_units vu3
                            WHERE vu3.venue_id = br.venue_id AND vu3.is_active = true
                        ) AS total_units
                    FROM booking_requests br
                    LEFT JOIN venue_units vu2 ON vu2.id = br.venue_unit_id
                    WHERE br.group_id IN ({placeholders})
                    GROUP BY br.group_id, br.venue_id
                    """,
                    list(group_ids),
                )
                for grow in cur.fetchall():
                    gid, unit_names_arr, units_booked, total_units = grow
                    unit_names_arr = unit_names_arr or []
                    # Убираем None из list[BookingRequest] = []
        for row in rows:
            (
                rid, roid, org_name, vid, venue_name, venue_unit_id,
                unit_name, group_id,
                desired_date, desired_start, desired_end,
                rstatus, contact_name, contact_phone, contact_email,
                telegram_user_id, telegram_chat_id,
                message, staff_comment, processed_by, processed_at,
                created_at, updated_at
            ) = row

            portion_label = ""
            group_unit_names = ""

            if group_id and group_id in group_info:
                portion_label = group_info[group_id]["portion_label"]
                group_unit_names = group_info[group_id]["unit_names"]
            elif venue_unit_id and not group_id:
                # Одиночная заявка на конкретный unit
                if vid not in venue_total_cache:
                    with conn.cursor() as cur2:
                        cur2.execute(
                            "SELECT COUNT(*) FROM venue_units WHERE venue_id=%s AND is_active=true",
                            (vid,),
                        )
                        venue_total_cache[vid] = cur2.fetchone()[0]
                total = venue_total_cache[vid]
                portion_label = _compute_portion_label(1, total)
                group_unit_names = unit_name or ""

            out.append(BookingRequest(
                id=rid,
                org_id=roid,
                org_name=org_name,
                venue_id=vid,
                venue_name=venue_name,
                venue_unit_id=venue_unit_id,
                unit_name=unit_name,
                group_id=group_id,
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
                portion_label=portion_label,
                group_unit_names=group_unit_names,
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
) -> int:
    """
    Меняет статус заявки и всех связанных (по group_id).
    Возвращает количество обновлённых заявок.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Получаем group_id
            cur.execute(
                "SELECT group_id FROM public.booking_requests WHERE id = %s",
                (request_id,),
            )
            row = cur.fetchone()
            if not row:
                return 0

            group_id = row[0]

            if group_id:
                # Обновляем все заявки группы
                if staff_comment is None:
                    cur.execute(
                        """
                        UPDATE public.booking_requests
                           SET status = %s,
                               processed_by = %s,
                               processed_at = now(),
                               updated_at = now()
                         WHERE group_id = %s
                        """,
                        (status, user_id, group_id),
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
                         WHERE group_id = %s
                        """,
                        (status, staff_comment, user_id, group_id),
                    )
            else:
                # Одиночная заявка
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

            updated_count = cur.rowcount

        conn.commit()
        return updated_count
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
