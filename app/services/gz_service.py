from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Dict, Any, Iterable

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


GZ_EDIT_ROLES = {"admin"}  # при необходимости расширьте: {"admin", "manager"}


def _norm_role(role_code: str) -> str:
    return (role_code or "").strip().lower()


def _admin(role_code: str) -> bool:
    return _norm_role(role_code) == "admin"


def _require_gz_view(*, user_id: int, role_code: str) -> None:
    if not user_id:
        raise PermissionError("Недостаточно прав: просмотр ГЗ запрещён")

def _require_gz_edit(*, user_id: int, role_code: str) -> None:
    _require_gz_view(user_id=user_id, role_code=role_code)
    if _admin(role_code):
        return
    if not list_accessible_org_ids(user_id=int(user_id), for_edit=True):
        raise PermissionError("Недостаточно прав: редактирование ГЗ запрещено")

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


# ---------------- helpers (access) ----------------

def list_accessible_org_ids(*, user_id: int, for_edit: bool = False) -> List[int]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT org_id
                FROM public.app_user_org_permissions
                WHERE user_id=%s AND { "can_edit" if for_edit else "can_view" }=true
                ORDER BY org_id
                """,
                (int(user_id),),
            )
            return [int(r[0]) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)


def _require_org_access_for_edit(*, user_id: int, role_code: str, org_ids: Iterable[int]) -> None:
    """
    Для не-admin запрещаем привязку/редактирование тренера на "чужих" org.
    """
    if _admin(role_code):
        return

    allowed = set(list_accessible_org_ids(user_id=int(user_id), for_edit=True))
    requested = {int(x) for x in org_ids if x is not None}
    if not requested:
        raise PermissionError("Нужно выбрать хотя бы одно доступное учреждение")
    if not requested.issubset(allowed):
        raise PermissionError("Нельзя назначить тренера на учреждения, к которым нет доступа")


# ---------------- coaches ----------------

def create_coach(*, user_id: int, role_code: str, full_name: str, comment: str = "") -> int:
    _require_gz_edit(user_id=user_id, role_code=role_code)

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


def update_coach(*, user_id: int, role_code: str, coach_id: int, full_name: str, comment: str = "") -> None:
    _require_gz_edit(user_id=user_id, role_code=role_code)

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


def set_coach_active(*, user_id: int, role_code: str, coach_id: int, is_active: bool) -> None:
    _require_gz_edit(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.gz_coaches SET is_active=%s WHERE id=%s",
                (bool(is_active), int(coach_id)),
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


def get_coach_org_ids(*, user_id: int, role_code: str, coach_id: int) -> List[int]:
    _require_gz_view(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT org_id FROM public.gz_coach_orgs WHERE coach_id=%s ORDER BY org_id",
                (int(coach_id),),
            )
            orgs = [int(r[0]) for r in cur.fetchall()]

        # для не-admin возвращаем только те org, которые доступны пользователю
        if _admin(role_code):
            return orgs

        allowed = set(list_accessible_org_ids(user_id=int(user_id)))
        return [oid for oid in orgs if oid in allowed]
    finally:
        if conn:
            put_conn(conn)


def set_coach_orgs(*, user_id: int, role_code: str, coach_id: int, org_ids: Iterable[int]) -> None:
    _require_gz_edit(user_id=user_id, role_code=role_code)
    _require_org_access_for_edit(user_id=user_id, role_code=role_code, org_ids=org_ids)

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
    user_id: Optional[int] = None,
    role_code: str = "",
) -> List[GzCoach]:
    if user_id is not None:
        _require_gz_view(user_id=int(user_id), role_code=role_code)

    search = (search or "").strip()
    org_ids_list = [int(x) for x in org_ids] if org_ids is not None else None

    accessible_orgs: Optional[List[int]] = None
    if not _admin(role_code):
        if user_id is None:
            return []
        accessible_orgs = list_accessible_org_ids(user_id=int(user_id))
        if not accessible_orgs:
            return []

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
            need_org_filter = (org_id is not None) or (org_ids_list is not None) or (accessible_orgs is not None)
            if need_org_filter:
                joins += " JOIN public.gz_coach_orgs co ON co.coach_id = c.id "

                if org_id is not None:
                    where.append("co.org_id = %(org_id)s")
                    params["org_id"] = int(org_id)

                if org_ids_list is not None:
                    if not org_ids_list:
                        return []
                    where.append("co.org_id = ANY(%(org_ids)s)")
                    params["org_ids"] = org_ids_list

                if accessible_orgs is not None:
                    where.append("co.org_id = ANY(%(acc_orgs)s)")
                    params["acc_orgs"] = accessible_orgs

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
    user_id: Optional[int] = None,
    role_code: str = "",
) -> List[GzGroup]:
    if user_id is not None:
        _require_gz_view(user_id=int(user_id), role_code=role_code)

    search = (search or "").strip()
    org_ids_list = [int(x) for x in org_ids] if org_ids is not None else None

    accessible_orgs: Optional[List[int]] = None
    if not _admin(role_code):
        if user_id is None:
            return []
        accessible_orgs = list_accessible_org_ids(user_id=int(user_id))
        if not accessible_orgs:
            return []

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive:
                where.append("g.is_active = true")
                where.append("c.is_active = true")

            joins = ""
            need_org_filter = (org_id is not None) or (org_ids_list is not None) or (accessible_orgs is not None)
            if need_org_filter:
                joins += " JOIN public.gz_coach_orgs co ON co.coach_id = c.id "

                if org_id is not None:
                    where.append("co.org_id = %(org_id)s")
                    params["org_id"] = int(org_id)

                if org_ids_list is not None:
                    if not org_ids_list:
                        return []
                    where.append("co.org_id = ANY(%(org_ids)s)")
                    params["org_ids"] = org_ids_list

                if accessible_orgs is not None:
                    where.append("co.org_id = ANY(%(acc_orgs)s)")
                    params["acc_orgs"] = accessible_orgs

            if search:
                where.append("(c.full_name ILIKE %(q)s OR g.group_year ILIKE %(q)s)")
                params["q"] = f"%{search}%"

            sql = f"""
                SELECT DISTINCT
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
                {joins}
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
    *,
    user_id: int,
    role_code: str,
    coach_id: int,
    group_year: str,
    notes: str = "",
    is_free: bool = False,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
) -> int:
    _require_gz_edit(user_id=user_id, role_code=role_code)

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
    *,
    user_id: int,
    role_code: str,
    group_id: int,
    coach_id: int,
    group_year: str,
    notes: str = "",
    is_free: bool = False,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
) -> None:
    _require_gz_edit(user_id=user_id, role_code=role_code)

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


def set_group_active(*, user_id: int, role_code: str, group_id: int, is_active: bool) -> None:
    _require_gz_edit(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.gz_groups SET is_active=%s WHERE id=%s",
                (bool(is_active), int(group_id)),
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


def list_active_gz_groups_for_booking(*, org_id: Optional[int] = None) -> List[Dict]:
    # как было (это просто справочник)
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


def list_coach_orgs_map(*, include_inactive_orgs: bool = False, org_ids: Optional[Iterable[int]] = None) -> Dict[int, List[str]]:
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
