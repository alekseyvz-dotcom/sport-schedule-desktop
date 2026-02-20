# app/services/org_closures_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.services.access_service import get_org_access


@dataclass(frozen=True)
class OrgClosure:
    id: int
    org_id: int
    date_from: date
    date_to: date
    reason: Optional[str]
    is_active: bool


def _require_org_edit(*, user_id: int, role_code: str, org_id: int) -> None:
    acc = get_org_access(user_id=user_id, role_code=role_code, org_id=org_id)
    if not acc.can_edit:
        raise PermissionError("Недостаточно прав: редактирование учреждения запрещено")


def list_org_closures(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    include_inactive: bool = False,
) -> List[OrgClosure]:
    # просмотр закрытий логично разрешать тем, кто может view учреждение,
    # но у вас в сервисах обычно гейт по edit. Сделаем мягче: can_edit для изменений,
    # а list — по can_view. Однако get_org_access возвращает can_view/can_edit, используем can_view.
    acc = get_org_access(user_id=user_id, role_code=role_code, org_id=org_id)
    if not acc.can_view:
        raise PermissionError("Недостаточно прав: просмотр учреждения запрещён")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT id, org_id, date_from, date_to, reason, is_active
                FROM public.org_closures
                WHERE org_id = %(org_id)s
            """
            params = {"org_id": int(org_id)}
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY date_from DESC, id DESC"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                OrgClosure(
                    id=int(r["id"]),
                    org_id=int(r["org_id"]),
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


def create_org_closure(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    date_from: date,
    date_to: date,
    reason: str = "",
) -> int:
    _require_org_edit(user_id=user_id, role_code=role_code, org_id=org_id)

    if date_to < date_from:
        raise ValueError("Дата 'по' должна быть >= даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.org_closures(org_id, date_from, date_to, reason, is_active)
                    VALUES (%s, %s, %s, %s, true)
                    RETURNING id
                    """,
                    (int(org_id), date_from, date_to, (reason or "").strip() or None),
                )
                return int(cur.fetchone()[0])
    finally:
        if conn:
            put_conn(conn)


def update_org_closure(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    closure_id: int,
    date_from: date,
    date_to: date,
    reason: str = "",
    is_active: bool = True,
) -> None:
    _require_org_edit(user_id=user_id, role_code=role_code, org_id=org_id)

    if date_to < date_from:
        raise ValueError("Дата 'по' должна быть >= даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.org_closures
                    SET date_from=%s, date_to=%s, reason=%s, is_active=%s
                    WHERE id=%s AND org_id=%s
                    """,
                    (
                        date_from,
                        date_to,
                        (reason or "").strip() or None,
                        bool(is_active),
                        int(closure_id),
                        int(org_id),
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError("Период закрытия не найден")
    finally:
        if conn:
            put_conn(conn)


def set_org_closure_active(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    closure_id: int,
    is_active: bool,
) -> None:
    _require_org_edit(user_id=user_id, role_code=role_code, org_id=org_id)

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE public.org_closures
                    SET is_active=%s
                    WHERE id=%s AND org_id=%s
                    """,
                    (bool(is_active), int(closure_id), int(org_id)),
                )
                if cur.rowcount != 1:
                    raise ValueError("Период закрытия не найден")
    finally:
        if conn:
            put_conn(conn)
