from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Dict, Any, Iterable

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
    group_year: str
    notes: Optional[str]
    is_active: bool
    is_free: bool
    period_from: Optional[date]
    period_to: Optional[date]


# ---------------- coaches ----------------

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


def get_coach_org_ids(coach_id: int) -> List[int]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT org_id FROM public.gz_coach_orgs WHERE coach_id=%s ORDER BY org_id",
                (int(coach_id),),
            )
            return [int(r[0]) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)


def set_coach_orgs(coach_id: int, org_ids: Iterable[int]) -> None:
    org_ids_list = sorted({int(x) for x in org_ids if x is not None})

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.gz_coach_orgs WHERE coach_id=%s", (int(coach_id),))
            if org_ids_list:
                cur.executemany(
                    "INSERT INTO public.gz_coach_orgs(coach_id, org_id) VALUES (%s, %s)",
                    [(int(coach_id), int(oid)) for oid in org_ids_list],
                )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def list_coaches(
    search: str = "",
    include_inactive: bool = False,
    *,
    org_id: Optional[int] = None,
    org_ids: Optional[Iterable[int]] = None,
) -> List[GzCoach]:
    search = (search or "").strip()
    org_ids_list = [int(x) for x in org_ids] if org_ids is not None else None

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

            joins = ""
            if org_id is not None or org_ids_list is not None:
                joins += " JOIN public.gz_coach_orgs co ON co.coach_id = c.id "

                if org_id is not None:
                    where.append("co.org_id = %(org_id)s")
                    params["org_id"] = int(org_id)

                if org_ids_list is not None:
                    if not org_ids_list:
                        return []
                    where.append("co.org_id = ANY(%(org_ids)s)")
                    params["org_ids"] = org_ids_list

            sql = f"""
                SELECT DISTINCT c.id, c.full_name, c.comment, c.is_active
                FROM public.gz_coaches c
                {joins}
            """
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


# ---------------- groups ----------------

def list_groups(
    search: str = "",
    include_inactive: bool = False,
    *,
    org_id: Optional[int] = None,
    org_ids: Optional[Iterable[int]] = None,
) -> List[GzGroup]:
    search = (search or "").strip()
    org_ids_list = [int(x) for x in org_ids] if org_ids is not None else None

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive:
                where.append("g.is_active = true")
                where.append("c.is_active = true")

            # фильтр по объектам через привязку тренера
            if org_id is not None or org_ids_list is not None:
                where.append("EXISTS (SELECT 1 FROM public.gz_coach_orgs co WHERE co.coach_id = c.id"
                             + (" AND co.org_id = %(org_id)s" if org_id is not None else "")
                             + (" AND co.org_id = ANY(%(org_ids)s)" if org_ids_list is not None else "")
                             + ")")
                if org_id is not None:
                    params["org_id"] = int(org_id)
                if org_ids_list is not None:
                    if not org_ids_list:
                        return []
                    params["org_ids"] = org_ids_list

            if search:
                where.append("(c.full_name ILIKE %(q)s OR g.group_year ILIKE %(q)s)")
                params["q"] = f"%{search}%"

            sql = """
                SELECT
                    g.id,
                    g.coach_id,
                    c.full_name AS coach_name,
                    g.group_year,
                    g.notes,
                    g.is_active,
                    g.is_free,
                    g.period_from,
                    g.period_to
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
                    group_year=str(r["group_year"] or "").strip(),
                    notes=r.get("notes"),
                    is_active=bool(r["is_active"]),
                    is_free=bool(r.get("is_free")),
                    period_from=r.get("period_from"),
                    period_to=r.get("period_to"),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def create_group(
    coach_id: int,
    group_year: str,
    notes: str = "",
    *,
    is_free: bool = False,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
) -> int:
    group_year = (group_year or "").strip()
    if not group_year:
        raise ValueError("Группа обязательна")
    if period_from and period_to and period_to < period_from:
        raise ValueError("Дата 'по' не может быть раньше даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.gz_groups(coach_id, group_year, notes, is_active, is_free, period_from, period_to)
                VALUES (%s, %s, %s, true, %s, %s, %s)
                RETURNING id
                """,
                (
                    int(coach_id),
                    group_year,
                    (notes or "").strip() or None,
                    bool(is_free),
                    period_from,
                    period_to,
                ),
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

def update_group(
    group_id: int,
    coach_id: int,
    group_year: str,
    notes: str = "",
    *,
    is_free: bool = False,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
) -> None:
    group_year = (group_year or "").strip()
    if not group_year:
        raise ValueError("Группа обязательна")
    if period_from and period_to and period_to < period_from:
        raise ValueError("Дата 'по' не может быть раньше даты 'с'")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.gz_groups
                SET coach_id=%s, group_year=%s, notes=%s,
                    is_free=%s, period_from=%s, period_to=%s
                WHERE id=%s
                """,
                (
                    int(coach_id),
                    group_year,
                    (notes or "").strip() or None,
                    bool(is_free),
                    period_from,
                    period_to,
                    int(group_id),
                ),
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


def list_active_gz_groups_for_booking(*, org_id: Optional[int] = None) -> List[Dict]:
    """
    [{id, name, is_free}]
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            params: Dict[str, Any] = {}
            where = ["g.is_active = true", "c.is_active = true"]

            joins = ""
            if org_id is not None:
                joins = "JOIN public.gz_coach_orgs co ON co.coach_id = c.id"
                where.append("co.org_id = %(org_id)s")
                params["org_id"] = int(org_id)

            cur.execute(
                f"""
                SELECT g.id, c.full_name AS coach_name, g.group_year, g.is_free
                FROM public.gz_groups g
                JOIN public.gz_coaches c ON c.id = g.coach_id
                {joins}
                WHERE {" AND ".join(where)}
                ORDER BY c.full_name, g.group_year
                """,
                params,
            )
            rows = cur.fetchall()
            return [
                {
                    "id": int(r["id"]),
                    "name": f"{r['coach_name']} — {str(r['group_year'] or '').strip()}",
                    "is_free": bool(r.get("is_free", False)),
                }
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)

def list_coach_orgs_map(
    *,
    include_inactive_orgs: bool = False,
    org_ids: Optional[Iterable[int]] = None,
) -> Dict[int, List[str]]:
    """
    Возвращает {coach_id: [org_name, ...]} (отсортировано по названию).
    Можно ограничить org_ids (например, доступными пользователю).
    """
    org_ids_list = [int(x) for x in org_ids] if org_ids is not None else None

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive_orgs:
                where.append("o.is_active = true")

            if org_ids_list is not None:
                if not org_ids_list:
                    return {}
                where.append("co.org_id = ANY(%(org_ids)s)")
                params["org_ids"] = org_ids_list

            sql = """
                SELECT co.coach_id, o.name AS org_name
                FROM public.gz_coach_orgs co
                JOIN public.sport_orgs o ON o.id = co.org_id
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY co.coach_id, o.name"

            cur.execute(sql, params)
            rows = cur.fetchall()

            out: Dict[int, List[str]] = {}
            for r in rows:
                out.setdefault(int(r["coach_id"]), []).append(str(r["org_name"]))
            return out
    finally:
        if conn:
            put_conn(conn)


def list_coach_orgs_map_full(
    *,
    include_inactive_orgs: bool = False,
    org_ids: Optional[Iterable[int]] = None,
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Возвращает {coach_id: [{"id": org_id, "name": org_name}, ...]}
    (полезно, если дальше захотите фильтровать/показывать точнее).
    """
    org_ids_list = [int(x) for x in org_ids] if org_ids is not None else None

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive_orgs:
                where.append("o.is_active = true")

            if org_ids_list is not None:
                if not org_ids_list:
                    return {}
                where.append("co.org_id = ANY(%(org_ids)s)")
                params["org_ids"] = org_ids_list

            sql = """
                SELECT co.coach_id, o.id AS org_id, o.name AS org_name
                FROM public.gz_coach_orgs co
                JOIN public.sport_orgs o ON o.id = co.org_id
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY co.coach_id, o.name"

            cur.execute(sql, params)
            rows = cur.fetchall()

            out: Dict[int, List[Dict[str, Any]]] = {}
            for r in rows:
                out.setdefault(int(r["coach_id"]), []).append({"id": int(r["org_id"]), "name": str(r["org_name"])})
            return out
    finally:
        if conn:
            put_conn(conn)
