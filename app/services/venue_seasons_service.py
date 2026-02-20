# app/services/venue_seasons_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.services.access_service import get_org_access


@dataclass(frozen=True)
class VenueSeasonOverride:
    id: int
    venue_id: int
    season_year: int
    title: str
    date_from: date
    date_to: date
    is_active: bool


def _require_venue_edit(*, user_id: int, role_code: str, venue_id: int) -> int:
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


def list_season_overrides(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    include_inactive: bool = False,
) -> List[VenueSeasonOverride]:
    _require_venue_edit(user_id=user_id, role_code=role_code, venue_id=venue_id)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT id, venue_id, season_year, title, date_from, date_to, is_active
                FROM public.venue_season_overrides
                WHERE venue_id = %(venue_id)s
            """
            params = {"venue_id": int(venue_id)}
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY season_year DESC, id DESC"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                VenueSeasonOverride(
                    id=int(r["id"]),
                    venue_id=int(r["venue_id"]),
                    season_year=int(r["season_year"]),
                    title=str(r.get("title") or ""),
                    date_from=r["date_from"],
                    date_to=r["date_to"],
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def upsert_season_override(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    season_year: int,
    date_from: date,
    date_to: date,
    title: str = "",
    is_active: bool = True,
) -> int:
    """
    Делает insert/update активной записи на (venue_id, season_year).
    У вас есть UNIQUE индекс uq_venue_season_overrides_one_active (частичный),
    поэтому проще:
      - деактивировать старую активную запись в году
      - вставить новую активную
    """
    _require_venue_edit(user_id=user_id, role_code=role_code, venue_id=venue_id)

    if not (2000 <= int(season_year) <= 2100):
        raise ValueError("Год должен быть в диапазоне 2000..2100")

    if date_from.year != int(season_year) or date_to.year != int(season_year):
        raise ValueError("date_from/date_to должны быть в указанном году")

    if date_to < date_from:
        raise ValueError("Дата 'по' должна быть >= даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                # деактивируем старую активную запись на этот год
                cur.execute(
                    """
                    UPDATE public.venue_season_overrides
                    SET is_active=false
                    WHERE venue_id=%s AND season_year=%s AND is_active=true
                    """,
                    (int(venue_id), int(season_year)),
                )

                # вставляем новую
                cur.execute(
                    """
                    INSERT INTO public.venue_season_overrides(
                        venue_id, season_year, title, date_from, date_to, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        int(venue_id),
                        int(season_year),
                        (title or "").strip(),
                        date_from,
                        date_to,
                        bool(is_active),
                    ),
                )
                return int(cur.fetchone()[0])
    finally:
        if conn:
            put_conn(conn)


def set_season_override_active(
    *,
    user_id: int,
    role_code: str,
    venue_id: int,
    override_id: int,
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
                    UPDATE public.venue_season_overrides
                    SET is_active=%s
                    WHERE id=%s AND venue_id=%s
                    """,
                    (bool(is_active), int(override_id), int(venue_id)),
                )
                if cur.rowcount != 1:
                    raise ValueError("Сезон не найден")
    finally:
        if conn:
            put_conn(conn)
