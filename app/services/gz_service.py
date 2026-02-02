from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from psycopg2.extras import RealDictCursor
from app.db import get_conn, put_conn


@dataclass(frozen=True)
class GzCoach:
    id: int
    full_name: str
    comment: Optional[str]
    is_active: bool


@dataclass(frozen=True)
class GzGroup:
    id: int
    coach_id: int
    coach_name: str
    group_year: int
    notes: Optional[str]
    is_active: bool

def update_coach(coach_id: int, full_name: str, comment: str = "") -> None:
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValueError("ФИО тренера не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.gz_coaches
                SET full_name=%s, comment=%s
                WHERE id=%s
                """,
                (full_name, (comment or "").strip() or None, int(coach_id)),
            )
            if cur.rowcount != 1:
                raise ValueError("Тренер не найден")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def set_coach_active(coach_id: int, is_active: bool) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.gz_coaches SET is_active=%s WHERE id=%s",
                (bool(is_active), int(coach_id)),
            )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)

def list_coaches(search: str = "", include_inactive: bool = False) -> List[GzCoach]:
    search = (search or "").strip()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive:
                where.append("c.is_active = true")
            if search:
                where.append("c.full_name ILIKE %(q)s")
                params["q"] = f"%{search}%"

            sql = "SELECT c.id, c.full_name, c.comment, c.is_active FROM public.gz_coaches c"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY c.full_name"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                GzCoach(
                    id=int(r["id"]),
                    full_name=str(r["full_name"]),
                    comment=r.get("comment"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_coach(full_name: str, comment: str = "") -> int:
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValueError("ФИО тренера не может быть пустым")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.gz_coaches(full_name, comment, is_active)
                VALUES (%s, %s, true)
                RETURNING id
                """,
                (full_name, (comment or "").strip() or None),
            )
            new_id = int(cur.fetchone()[0])
        conn.commit()
        return new_id
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def list_groups(search: str = "", include_inactive: bool = False) -> List[GzGroup]:
    search = (search or "").strip()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive:
                where.append("g.is_active = true")
                where.append("c.is_active = true")

            if search:
                where.append("(c.full_name ILIKE %(q)s OR CAST(g.group_year AS text) ILIKE %(q)s)")
                params["q"] = f"%{search}%"

            sql = """
                SELECT
                    g.id, g.coach_id, c.full_name AS coach_name,
                    g.group_year, g.notes, g.is_active
                FROM public.gz_groups g
                JOIN public.gz_coaches c ON c.id = g.coach_id
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY c.full_name, g.group_year"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                GzGroup(
                    id=int(r["id"]),
                    coach_id=int(r["coach_id"]),
                    coach_name=str(r["coach_name"]),
                    group_year=int(r["group_year"]),
                    notes=r.get("notes"),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_group(coach_id: int, group_year: int, notes: str = "") -> int:
    if not int(group_year):
        raise ValueError("Год группы обязателен")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.gz_groups(coach_id, group_year, notes, is_active)
                VALUES (%s, %s, %s, true)
                RETURNING id
                """,
                (int(coach_id), int(group_year), (notes or "").strip() or None),
            )
            new_id = int(cur.fetchone()[0])
        conn.commit()
        return new_id
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def update_group(group_id: int, coach_id: int, group_year: int, notes: str = "") -> None:
    if not int(group_year):
        raise ValueError("Год группы обязателен")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.gz_groups
                SET coach_id=%s, group_year=%s, notes=%s
                WHERE id=%s
                """,
                (int(coach_id), int(group_year), (notes or "").strip() or None, int(group_id)),
            )
            if cur.rowcount != 1:
                raise ValueError("Группа не найдена")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def set_group_active(group_id: int, is_active: bool) -> None:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.gz_groups SET is_active=%s WHERE id=%s",
                (bool(is_active), int(group_id)),
            )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)
