from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Dict, Any

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


# какие роли могут редактировать контрагентов
TENANTS_EDIT_ROLES = {"admin"}  # при необходимости добавьте: {"admin", "manager"}


def _norm_role(role_code: str) -> str:
    return (role_code or "").strip().lower()


def _require_tenants_view(*, user_id: int, role_code: str) -> None:
    # сейчас: всем авторизованным можно смотреть
    if not user_id:
        raise PermissionError("Недостаточно прав: просмотр контрагентов запрещён")


def _require_tenants_edit(*, user_id: int, role_code: str) -> None:
    _require_tenants_view(user_id=user_id, role_code=role_code)
    if _norm_role(role_code) not in TENANTS_EDIT_ROLES:
        raise PermissionError("Недостаточно прав: редактирование контрагентов запрещено")


def _tlog(msg: str) -> None:
    # оставил ваш лог как есть
    try:
        import os
        import tempfile
        from datetime import datetime

        path = os.path.join(tempfile.gettempdir(), "tenant_debug.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


@dataclass(frozen=True)
class Tenant:
    id: int
    name: str
    inn: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    comment: Optional[str]
    is_active: bool

    contact_name: Optional[str]
    obligation_kind: Optional[str]
    contract_no: Optional[str]
    contract_date: Optional[date]
    contract_valid_from: Optional[date]
    contract_valid_to: Optional[date]
    docs_delivery_method: Optional[str]
    status: Optional[str]
    contract_signed: bool
    attached_in_1c: bool
    has_ds: bool
    notes: Optional[str]

    tenant_kind: str  # 'legal' | 'person'
    rent_kind: str  # 'long_term' | 'one_time'


def list_tenants(
    *,
    user_id: int,
    role_code: str,
    search: str = "",
    include_inactive: bool = False,
) -> List[Tenant]:
    _require_tenants_view(user_id=user_id, role_code=role_code)

    search = (search or "").strip()
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            where = []
            params: Dict[str, Any] = {}

            if not include_inactive:
                where.append("t.is_active = true")

            if search:
                where.append("(t.name ILIKE %(q)s OR t.inn ILIKE %(q)s OR t.phone ILIKE %(q)s)")
                params["q"] = f"%{search}%"

            sql = """
                SELECT
                    t.id, t.name, t.inn, t.phone, t.email, t.comment, t.is_active,
                    t.contact_name, t.obligation_kind, t.contract_no,
                    t.contract_date, t.contract_valid_from, t.contract_valid_to,
                    t.docs_delivery_method, t.status, t.contract_signed,
                    t.attached_in_1c, t.has_ds, t.notes,
                    t.tenant_kind, t.rent_kind
                FROM public.tenants t
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY t.name"

            cur.execute(sql, params)
            rows = cur.fetchall()
            return [
                Tenant(
                    id=int(r["id"]),
                    name=str(r["name"]),
                    inn=r.get("inn"),
                    phone=r.get("phone"),
                    email=r.get("email"),
                    comment=r.get("comment"),
                    is_active=bool(r["is_active"]),
                    contact_name=r.get("contact_name"),
                    obligation_kind=r.get("obligation_kind"),
                    contract_no=r.get("contract_no"),
                    contract_date=r.get("contract_date"),
                    contract_valid_from=r.get("contract_valid_from"),
                    contract_valid_to=r.get("contract_valid_to"),
                    docs_delivery_method=r.get("docs_delivery_method"),
                    status=r.get("status"),
                    contract_signed=bool(r.get("contract_signed") or False),
                    attached_in_1c=bool(r.get("attached_in_1c") or False),
                    has_ds=bool(r.get("has_ds") or False),
                    notes=r.get("notes"),
                    tenant_kind=str(r.get("tenant_kind") or "legal"),
                    rent_kind=str(r.get("rent_kind") or "long_term"),
                )
                for r in rows
            ]
    finally:
        if conn:
            put_conn(conn)


def get_tenant(*, user_id: int, role_code: str, tenant_id: int) -> Tenant:
    _require_tenants_view(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    t.id, t.name, t.inn, t.phone, t.email, t.comment, t.is_active,
                    t.contact_name, t.obligation_kind, t.contract_no,
                    t.contract_date, t.contract_valid_from, t.contract_valid_to,
                    t.docs_delivery_method, t.status, t.contract_signed,
                    t.attached_in_1c, t.has_ds, t.notes,
                    t.tenant_kind, t.rent_kind
                FROM public.tenants t
                WHERE t.id = %s
                """,
                (int(tenant_id),),
            )
            r = cur.fetchone()
            if not r:
                raise ValueError("Контрагент не найден")

            return Tenant(
                id=int(r["id"]),
                name=str(r["name"]),
                inn=r.get("inn"),
                phone=r.get("phone"),
                email=r.get("email"),
                comment=r.get("comment"),
                is_active=bool(r["is_active"]),
                contact_name=r.get("contact_name"),
                obligation_kind=r.get("obligation_kind"),
                contract_no=r.get("contract_no"),
                contract_date=r.get("contract_date"),
                contract_valid_from=r.get("contract_valid_from"),
                contract_valid_to=r.get("contract_valid_to"),
                docs_delivery_method=r.get("docs_delivery_method"),
                status=r.get("status"),
                contract_signed=bool(r.get("contract_signed") or False),
                attached_in_1c=bool(r.get("attached_in_1c") or False),
                has_ds=bool(r.get("has_ds") or False),
                notes=r.get("notes"),
                tenant_kind=str(r.get("tenant_kind") or "legal"),
                rent_kind=str(r.get("rent_kind") or "long_term"),
            )
    finally:
        if conn:
            put_conn(conn)


def create_tenant(*, user_id: int, role_code: str, **data) -> int:
    _require_tenants_edit(user_id=user_id, role_code=role_code)

    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Название контрагента не может быть пустым")

    tenant_kind = (data.get("tenant_kind") or "legal").strip()
    rent_kind = (data.get("rent_kind") or "long_term").strip()

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.tenants(
                    name, inn, phone, email, comment, is_active,
                    contact_name, obligation_kind, contract_no,
                    contract_date, contract_valid_from, contract_valid_to,
                    docs_delivery_method, status, contract_signed,
                    attached_in_1c, has_ds, notes,
                    tenant_kind, rent_kind
                )
                VALUES (
                    %(name)s, %(inn)s, %(phone)s, %(email)s, %(comment)s, true,
                    %(contact_name)s, %(obligation_kind)s, %(contract_no)s,
                    %(contract_date)s, %(contract_valid_from)s, %(contract_valid_to)s,
                    %(docs_delivery_method)s, %(status)s, %(contract_signed)s,
                    %(attached_in_1c)s, %(has_ds)s, %(notes)s,
                    %(tenant_kind)s, %(rent_kind)s
                )
                RETURNING id
                """,
                {
                    "name": name,
                    "inn": (data.get("inn") or "").strip() or None,
                    "phone": (data.get("phone") or "").strip() or None,
                    "email": (data.get("email") or "").strip() or None,
                    "comment": (data.get("comment") or "").strip() or None,
                    "contact_name": (data.get("contact_name") or "").strip() or None,
                    "obligation_kind": (data.get("obligation_kind") or "").strip() or None,
                    "contract_no": (data.get("contract_no") or "").strip() or None,
                    "contract_date": data.get("contract_date"),
                    "contract_valid_from": data.get("contract_valid_from"),
                    "contract_valid_to": data.get("contract_valid_to"),
                    "docs_delivery_method": (data.get("docs_delivery_method") or "").strip() or None,
                    "status": (data.get("status") or "active").strip() or None,
                    "contract_signed": bool(data.get("contract_signed") or False),
                    "attached_in_1c": bool(data.get("attached_in_1c") or False),
                    "has_ds": bool(data.get("has_ds") or False),
                    "notes": (data.get("notes") or "").strip() or None,
                    "tenant_kind": tenant_kind,
                    "rent_kind": rent_kind,
                },
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


def update_tenant(*, user_id: int, role_code: str, tenant_id: int, **data) -> None:
    _require_tenants_edit(user_id=user_id, role_code=role_code)

    _tlog(f"update_tenant CALLED tenant_id={tenant_id}, name={data.get('name')!r}")

    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Название контрагента не может быть пустым")

    tenant_kind = (data.get("tenant_kind") or "legal").strip()
    rent_kind = (data.get("rent_kind") or "long_term").strip()

    conn = None
    try:
        conn = get_conn()

        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user, inet_server_addr(), inet_server_port();")
            _tlog("DBINFO: " + str(cur.fetchone()))
            cur.execute("show transaction_read_only;")
            _tlog("READ_ONLY: " + str(cur.fetchone()))

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.tenants
                SET
                    name=%(name)s,
                    inn=%(inn)s,
                    phone=%(phone)s,
                    email=%(email)s,
                    comment=%(comment)s,
                    contact_name=%(contact_name)s,
                    obligation_kind=%(obligation_kind)s,
                    contract_no=%(contract_no)s,
                    contract_date=%(contract_date)s,
                    contract_valid_from=%(contract_valid_from)s,
                    contract_valid_to=%(contract_valid_to)s,
                    docs_delivery_method=%(docs_delivery_method)s,
                    status=%(status)s,
                    contract_signed=%(contract_signed)s,
                    attached_in_1c=%(attached_in_1c)s,
                    has_ds=%(has_ds)s,
                    notes=%(notes)s,
                    tenant_kind=%(tenant_kind)s,
                    rent_kind=%(rent_kind)s
                WHERE id=%(id)s
                """,
                {
                    "id": int(tenant_id),
                    "name": name,
                    "inn": (data.get("inn") or "").strip() or None,
                    "phone": (data.get("phone") or "").strip() or None,
                    "email": (data.get("email") or "").strip() or None,
                    "comment": (data.get("comment") or "").strip() or None,
                    "contact_name": (data.get("contact_name") or "").strip() or None,
                    "obligation_kind": (data.get("obligation_kind") or "").strip() or None,
                    "contract_no": (data.get("contract_no") or "").strip() or None,
                    "contract_date": data.get("contract_date"),
                    "contract_valid_from": data.get("contract_valid_from"),
                    "contract_valid_to": data.get("contract_valid_to"),
                    "docs_delivery_method": (data.get("docs_delivery_method") or "").strip() or None,
                    "status": (data.get("status") or "active").strip() or None,
                    "contract_signed": bool(data.get("contract_signed") or False),
                    "attached_in_1c": bool(data.get("attached_in_1c") or False),
                    "has_ds": bool(data.get("has_ds") or False),
                    "notes": (data.get("notes") or "").strip() or None,
                    "tenant_kind": tenant_kind,
                    "rent_kind": rent_kind,
                },
            )
            rowcount = cur.rowcount

        _tlog(f"update_tenant rowcount={rowcount}")

        if rowcount != 1:
            raise RuntimeError(f"Контрагент id={tenant_id} не найден (rowcount={rowcount}).")

        conn.commit()
        _tlog("update_tenant commit OK")

    except Exception as e:
        _tlog(f"update_tenant ERROR: {type(e).__name__}: {e!r}")
        if conn:
            conn.rollback()
            _tlog("update_tenant rollback OK")
        raise

    finally:
        _tlog("update_tenant returning connection to pool")
        if conn:
            put_conn(conn)


def set_tenant_active(*, user_id: int, role_code: str, tenant_id: int, is_active: bool) -> None:
    _require_tenants_edit(user_id=user_id, role_code=role_code)

    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.tenants SET is_active=%s WHERE id=%s",
                (bool(is_active), int(tenant_id)),
            )
            if cur.rowcount != 1:
                raise ValueError("Контрагент не найден")
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            put_conn(conn)
