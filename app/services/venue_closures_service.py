# app/services/venue_closures_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.services.access_service import get_org_access


@dataclass(frozen=True)
class VenueClosure:
    id: int
    venue_id: int
    date_from: date
    date_to: date
    reason: Optional[str]
    is_active: bool


def _require_venue_edit(*, user_id: int, role_code: str, venue_id: int) -> int:
    """
    Проверяем права через org_id площадки.
    Возвращаем org_id, чтобы не делать второй запрос в UI.
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT org_id FROM public.venues WHERE id=%s", (int(venue_id),))
            row = cur.fetchone()
            if not row:
                raise ValueError("Площадка не найдена")
            org_id = int(row[0])
    finally:
        if conn:
            put_conn(conn)

    acc = get_org_access(user_id=user_id, role_code=role_code, org_id=org_id)
    if not acc.can_edit:
        raise PermissionError("Недостаточно прав: редактирование площадки запрещено")

    return org_id


def list_venue_closures(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    include_inactive: bool = False,
) -> List[VenueClosure]:
    # просмотр: как минимум can_view на org
    org_id = _require_venue_edit(user_id=user_id, role_code=role_code, venue_id=venue_id)  # edit check
    # если хотите разрешить просмотр без edit — скажи, ослабим

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT id, venue_id, date_from, date_to, reason, is_active
                FROM public.venue_closures
                WHERE venue_id = %(venue_id)s
            """
            params = {"venue_id": int(venue_id)}
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY date_from DESC, id DESC"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                VenueClosure(
                    id=int(r["id"]),
                    venue_id=int(r["venue_id"]),
                    date_from=r["date_from"],
                    date_to=r["date_to"],
                    reason=r.get("reason"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_venue_closure(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    date_from: date,
    date_to: date,
    reason: str = "",
) -> int:
    _require_venue_edit(user_id=user_id, role_code=role_code, venue_id=venue_id)

    if date_to < date_from:
        raise ValueError("Дата 'по' должна быть >= даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.venue_closures(venue_id, date_from, date_to, reason, is_active)
                    VALUES (%s, %s, %s, %s, true)
                    RETURNING id
                    """,
                    (int(venue_id), date_from, date_to, (reason or "").strip() or None),
                )
                return int(cur.fetchone()[0])
    finally:
        if conn:
            put_conn(conn)


def update_venue_closure(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    closure_id: int,
    date_from: date,
    date_to: date,
    reason: str = "",
    is_active: bool = True,
) -> None:
    _require_venue_edit(user_id=user_id, role_code=role_code, venue_id=venue_id)

    if date_to < date_from:
        raise ValueError("Дата 'по' должна быть >= даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.venue_closures
                    SET date_from=%s, date_to=%s, reason=%s, is_active=%s
                    WHERE id=%s AND venue_id=%s
                    """,
                    (
                        date_from,
                        date_to,
                        (reason or "").strip() or None,
                        bool(is_active),
                        int(closure_id),
                        int(venue_id),
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError("Период закрытия не найден")
    finally:
        if conn:
            put_conn(conn)


def set_venue_closure_active(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    closure_id: int,
    is_active: bool,
) -> None:
    _require_venue_edit(user_id=user_id, role_code=role_code, venue_id=venue_id)

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.venue_closures
                    SET is_active=%s
                    WHERE id=%s AND venue_id=%s
                    """,
                    (bool(is_active), int(closure_id), int(venue_id)),
                )
                if cur.rowcount != 1:
                    raise ValueError("Период закрытия не найден")
    finally:
        if conn:
            put_conn(conn)
