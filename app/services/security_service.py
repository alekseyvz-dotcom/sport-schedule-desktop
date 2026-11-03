# app/services/security_service.py
"""
Данные Службы безопасности МФА (ТЗ, п. 1).

Два реестра по контрагенту (ПД) в разрезе учреждения:
  1. список спортсменов группы      — tenant_athletes
  2. согласованный список автомобилей — tenant_vehicles

Доступ — по той же модели, что и остальные разделы:
  • раздел     — app_permissions / app_user_permissions  (code = tab.security)
  • учреждение — app_user_org_permissions (can_view / can_edit)

Правило: СБ видит и ведёт данные только по выданным ей учреждениям.
Роль admin видит всё.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.services.access_service import get_org_access, list_allowed_org_ids

SECURITY_TAB_CODE = "tab.security"


# ──────────────────────────────────────────────────────────────────────────────
# модели
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SecurityAthlete:
    id: int
    tenant_id: int
    org_id: int
    full_name: str
    birth_date: Optional[date]
    document_no: Optional[str]
    comment: Optional[str]
    sort_order: int
    is_active: bool


@dataclass(frozen=True)
class SecurityVehicle:
    id: int
    tenant_id: int
    org_id: int
    plate_no: str
    brand_model: Optional[str]
    driver_name: Optional[str]
    seats: Optional[int]
    pass_valid_from: Optional[date]
    pass_valid_to: Optional[date]
    approved_at: Optional[datetime]
    approved_by_name: Optional[str]
    comment: Optional[str]
    sort_order: int
    is_active: bool


@dataclass(frozen=True)
class TenantSecuritySummary:
    tenant_id: int
    tenant_name: str
    tenant_kind: str
    athletes_total: int
    athletes_active: int
    vehicles_total: int
    vehicles_active: int
    has_presence: bool


# ──────────────────────────────────────────────────────────────────────────────
# доступ
# ──────────────────────────────────────────────────────────────────────────────

def _norm_role(role_code: str) -> str:
    return (role_code or "").strip().lower()


def _is_admin(role_code: str) -> bool:
    return _norm_role(role_code) == "admin"


def _require_security_view(*, user_id: int, role_code: str, org_id: int) -> None:
    """Просмотр: учреждение должно быть доступно пользователю."""
    if not user_id:
        raise PermissionError("Недостаточно прав: просмотр раздела запрещён")

    if _is_admin(role_code):
        return

    acc = get_org_access(int(user_id), str(role_code), int(org_id))
    if not acc.can_view:
        raise PermissionError(
            "Недостаточно прав: учреждение не доступно для этого пользователя"
        )


def _require_security_edit(*, user_id: int, role_code: str, org_id: int) -> None:
    """
    Изменение реестров СБ.

    СБ ведёт эти списки сама, поэтому достаточно доступа к учреждению —
    права на редактирование расписания здесь не требуются.
    """
    _require_security_view(user_id=user_id, role_code=role_code, org_id=int(org_id))


def list_security_org_ids(*, user_id: int, role_code: str) -> List[int]:
    """Учреждения, доступные в разделе СБ."""
    return list_allowed_org_ids(int(user_id), str(role_code))


# ──────────────────────────────────────────────────────────────────────────────
# контрагенты в разрезе учреждения
# ──────────────────────────────────────────────────────────────────────────────

def list_tenants_for_org(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    search: str = "",
    include_inactive: bool = False,
    only_with_presence: bool = True,
) -> List[TenantSecuritySummary]:
    """
    Контрагенты (ПД) со счётчиками по реестрам СБ.

    only_with_presence=True — только те, у кого есть правила или брони
    на площадках выбранного учреждения.
    """
    _require_security_view(user_id=user_id, role_code=role_code, org_id=int(org_id))

    search = (search or "").strip()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            params = {"org_id": int(org_id)}
            where = ["t.tenant_kind = 'person'"]

            if not include_inactive:
                where.append("t.is_active = true")

            if search:
                where.append("(t.name ILIKE %(q)s OR t.phone ILIKE %(q)s)")
                params["q"] = f"%{search}%"

            presence_sql = """
                (
                  EXISTS (
                    SELECT 1
                      FROM public.tenant_recurring_rules r
                      JOIN public.venue_units vu ON vu.id = r.venue_unit_id
                      JOIN public.venues v ON v.id = vu.venue_id
                     WHERE r.tenant_id = t.id
                       AND v.org_id = %(org_id)s
                  )
                  OR EXISTS (
                    SELECT 1
                      FROM public.bookings b
                      JOIN public.venues v2 ON v2.id = b.venue_id
                     WHERE b.tenant_id = t.id
                       AND v2.org_id = %(org_id)s
                  )
                )
            """
            if only_with_presence:
                where.append(presence_sql)

            sql = f"""
                SELECT
                    t.id,
                    t.name,
                    t.tenant_kind,
                    (SELECT COUNT(*) FROM public.tenant_athletes a
                      WHERE a.tenant_id = t.id AND a.org_id = %(org_id)s) AS athletes_total,
                    (SELECT COUNT(*) FROM public.tenant_athletes a2
                      WHERE a2.tenant_id = t.id AND a2.org_id = %(org_id)s
                        AND a2.is_active = true) AS athletes_active,
                    (SELECT COUNT(*) FROM public.tenant_vehicles v3
                      WHERE v3.tenant_id = t.id AND v3.org_id = %(org_id)s) AS vehicles_total,
                    (SELECT COUNT(*) FROM public.tenant_vehicles v4
                      WHERE v4.tenant_id = t.id AND v4.org_id = %(org_id)s
                        AND v4.is_active = true) AS vehicles_active,
                    {presence_sql} AS has_presence
                FROM public.tenants t
                WHERE {' AND '.join(where)}
                ORDER BY t.name
            """
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                TenantSecuritySummary(
                    tenant_id=int(r["id"]),
                    tenant_name=str(r["name"]),
                    tenant_kind=str(r.get("tenant_kind") or "person"),
                    athletes_total=int(r["athletes_total"] or 0),
                    athletes_active=int(r["athletes_active"] or 0),
                    vehicles_total=int(r["vehicles_total"] or 0),
                    vehicles_active=int(r["vehicles_active"] or 0),
                    has_presence=bool(r["has_presence"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


# ──────────────────────────────────────────────────────────────────────────────
# спортсмены
# ──────────────────────────────────────────────────────────────────────────────

def list_athletes(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    tenant_id: int,
    include_inactive: bool = True,
) -> List[SecurityAthlete]:
    _require_security_view(user_id=user_id, role_code=role_code, org_id=int(org_id))

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT id, tenant_id, org_id, full_name, birth_date,
                       document_no, comment, sort_order, is_active
                  FROM public.tenant_athletes
                 WHERE tenant_id = %(tenant_id)s
                   AND org_id = %(org_id)s
            """
            if not include_inactive:
                sql += " AND is_active = true"
            sql += " ORDER BY sort_order, full_name"

            cur.execute(sql, {"tenant_id": int(tenant_id), "org_id": int(org_id)})
            rows = cur.fetchall()
            return [
                SecurityAthlete(
                    id=int(r["id"]),
                    tenant_id=int(r["tenant_id"]),
                    org_id=int(r["org_id"]),
                    full_name=str(r["full_name"] or ""),
                    birth_date=r.get("birth_date"),
                    document_no=r.get("document_no"),
                    comment=r.get("comment"),
                    sort_order=int(r.get("sort_order") or 0),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def add_athlete(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    tenant_id: int,
    full_name: str,
    birth_date: Optional[date] = None,
    document_no: Optional[str] = None,
    comment: Optional[str] = None,
) -> int:
    _require_security_edit(user_id=user_id, role_code=role_code, org_id=int(org_id))

    name = (full_name or "").strip()
    if not name:
        raise ValueError("Укажите ФИО спортсмена.")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.tenant_athletes
                    (tenant_id, org_id, full_name, birth_date, document_no, comment)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    int(tenant_id), int(org_id), name, birth_date,
                    (document_no or "").strip() or None,
                    (comment or "").strip() or None,
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


def update_athlete(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    athlete_id: int,
    full_name: str,
    birth_date: Optional[date] = None,
    document_no: Optional[str] = None,
    comment: Optional[str] = None,
    is_active: bool = True,
) -> None:
    _require_security_edit(user_id=user_id, role_code=role_code, org_id=int(org_id))

    name = (full_name or "").strip()
    if not name:
        raise ValueError("Укажите ФИО спортсмена.")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.tenant_athletes
                   SET full_name = %s,
                       birth_date = %s,
                       document_no = %s,
                       comment = %s,
                       is_active = %s,
                       updated_at = now()
                 WHERE id = %s AND org_id = %s
                """,
                (
                    name, birth_date, (document_no or "").strip() or None,
                    (comment or "").strip() or None, bool(is_active),
                    int(athlete_id), int(org_id),
                ),
            )
            if cur.rowcount != 1:
                raise ValueError("Спортсмен не найден.")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def delete_athlete(*, user_id: int, role_code: str, org_id: int, athlete_id: int) -> None:
    _require_security_edit(user_id=user_id, role_code=role_code, org_id=int(org_id))

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.tenant_athletes WHERE id = %s AND org_id = %s",
                (int(athlete_id), int(org_id)),
            )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


# ──────────────────────────────────────────────────────────────────────────────
# автомобили
# ──────────────────────────────────────────────────────────────────────────────

def list_vehicles(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    tenant_id: int,
    include_inactive: bool = True,
) -> List[SecurityVehicle]:
    _require_security_view(user_id=user_id, role_code=role_code, org_id=int(org_id))

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            sql = """
                SELECT v.id, v.tenant_id, v.org_id, v.plate_no, v.brand_model,
                       v.driver_name, v.seats, v.pass_valid_from, v.pass_valid_to,
                       v.approved_at, v.comment, v.sort_order, v.is_active,
                       COALESCE(u.full_name, u.username, '') AS approved_by_name
                  FROM public.tenant_vehicles v
                  LEFT JOIN public.app_users u ON u.id = v.approved_by
                 WHERE v.tenant_id = %(tenant_id)s
                   AND v.org_id = %(org_id)s
            """
            if not include_inactive:
                sql += " AND v.is_active = true"
            sql += " ORDER BY v.sort_order, v.plate_no"

            cur.execute(sql, {"tenant_id": int(tenant_id), "org_id": int(org_id)})
            rows = cur.fetchall()
            return [
                SecurityVehicle(
                    id=int(r["id"]),
                    tenant_id=int(r["tenant_id"]),
                    org_id=int(r["org_id"]),
                    plate_no=str(r["plate_no"] or ""),
                    brand_model=r.get("brand_model"),
                    driver_name=r.get("driver_name"),
                    seats=(int(r["seats"]) if r.get("seats") is not None else None),
                    pass_valid_from=r.get("pass_valid_from"),
                    pass_valid_to=r.get("pass_valid_to"),
                    approved_at=r.get("approved_at"),
                    approved_by_name=(r.get("approved_by_name") or None),
                    comment=r.get("comment"),
                    sort_order=int(r.get("sort_order") or 0),
                    is_active=bool(r["is_active"]),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def add_vehicle(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    tenant_id: int,
    plate_no: str,
    brand_model: Optional[str] = None,
    driver_name: Optional[str] = None,
    seats: Optional[int] = None,
    pass_valid_from: Optional[date] = None,
    pass_valid_to: Optional[date] = None,
    comment: Optional[str] = None,
    approved: bool = True,
) -> int:
    """Добавляет автомобиль. approved=True фиксирует, кто и когда согласовал."""
    _require_security_edit(user_id=user_id, role_code=role_code, org_id=int(org_id))

    plate = normalize_plate(plate_no)
    if not plate:
        raise ValueError("Укажите государственный номер автомобиля.")
    if pass_valid_from and pass_valid_to and pass_valid_to < pass_valid_from:
        raise ValueError("Срок пропуска: дата «по» раньше даты «с».")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.tenant_vehicles
                    (tenant_id, org_id, plate_no, brand_model, driver_name, seats,
                     pass_valid_from, pass_valid_to, comment, approved_by, approved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s THEN now() ELSE NULL END)
                RETURNING id
                """,
                (
                    int(tenant_id), int(org_id), plate,
                    (brand_model or "").strip() or None,
                    (driver_name or "").strip() or None,
                    (int(seats) if seats not in (None, "") else None),
                    pass_valid_from, pass_valid_to,
                    (comment or "").strip() or None,
                    int(user_id) if approved else None,
                    bool(approved),
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


def update_vehicle(
    *,
    user_id: int,
    role_code: str,
    org_id: int,
    vehicle_id: int,
    plate_no: str,
    brand_model: Optional[str] = None,
    driver_name: Optional[str] = None,
    seats: Optional[int] = None,
    pass_valid_from: Optional[date] = None,
    pass_valid_to: Optional[date] = None,
    comment: Optional[str] = None,
    is_active: bool = True,
) -> None:
    _require_security_edit(user_id=user_id, role_code=role_code, org_id=int(org_id))

    plate = normalize_plate(plate_no)
    if not plate:
        raise ValueError("Укажите государственный номер автомобиля.")
    if pass_valid_from and pass_valid_to and pass_valid_to < pass_valid_from:
        raise ValueError("Срок пропуска: дата «по» раньше даты «с».")

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.tenant_vehicles
                   SET plate_no = %s,
                       brand_model = %s,
                       driver_name = %s,
                       seats = %s,
                       pass_valid_from = %s,
                       pass_valid_to = %s,
                       comment = %s,
                       is_active = %s,
                       updated_at = now()
                 WHERE id = %s AND org_id = %s
                """,
                (
                    plate, (brand_model or "").strip() or None,
                    (driver_name or "").strip() or None,
                    (int(seats) if seats not in (None, "") else None),
                    pass_valid_from, pass_valid_to,
                    (comment or "").strip() or None, bool(is_active),
                    int(vehicle_id), int(org_id),
                ),
            )
            if cur.rowcount != 1:
                raise ValueError("Автомобиль не найден.")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


def delete_vehicle(*, user_id: int, role_code: str, org_id: int, vehicle_id: int) -> None:
    _require_security_edit(user_id=user_id, role_code=role_code, org_id=int(org_id))

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.tenant_vehicles WHERE id = %s AND org_id = %s",
                (int(vehicle_id), int(org_id)),
            )
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)


# ──────────────────────────────────────────────────────────────────────────────
# утилиты
# ──────────────────────────────────────────────────────────────────────────────

def normalize_plate(value: str) -> str:
    """Приводит госномер к верхнему регистру без пробелов, дефисов и прочего."""
    raw = (value or "").upper()
    return "".join(ch for ch in raw if ch.isalnum())


def format_plate(value: str) -> str:
    """Показывает номер как есть; для пустого возвращает пустую строку."""
    return (value or "").strip()
