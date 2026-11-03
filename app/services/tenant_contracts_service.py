"""Contract history. Adding history does not alter the legacy current contract."""
from datetime import date

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn
from app.services.tenants_service import _require_tenants_view, _require_tenants_edit


def list_contracts(*, user_id: int, role_code: str, tenant_id: int):
    _require_tenants_view(user_id=user_id, role_code=role_code)
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, contract_no, contract_date, valid_from, valid_to,
                       contract_signed, attached_in_1c, has_ds, is_legacy
                  FROM public.tenant_contracts
                 WHERE tenant_id = %s
                 ORDER BY valid_from DESC NULLS LAST, id DESC
            """, (int(tenant_id),))
            return list(cur.fetchall())
    finally:
        put_conn(conn)


def add_contract(*, user_id: int, role_code: str, tenant_id: int,
                 contract_no: str, contract_date: date,
                 valid_from: date, valid_to: date,
                 contract_signed: bool = False, attached_in_1c: bool = False,
                 has_ds: bool = False):
    _require_tenants_edit(user_id=user_id, role_code=role_code)
    number = (contract_no or '').strip()
    if not number:
        raise ValueError('Укажите номер договора.')
    if not all(isinstance(d, date) for d in (contract_date, valid_from, valid_to)):
        raise ValueError('Укажите дату договора и срок его действия.')
    if valid_to < valid_from:
        raise ValueError('Дата окончания раньше даты начала.')
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Serializes additions for this tenant; does not change its legacy fields.
            cur.execute('SELECT id FROM public.tenants WHERE id = %s FOR UPDATE', (int(tenant_id),))
            if cur.fetchone() is None:
                raise ValueError('Контрагент не найден.')
            cur.execute('''
                SELECT 1 FROM public.tenant_contracts
                 WHERE tenant_id = %s AND contract_no = %s
                   AND contract_date = %s AND valid_from = %s AND valid_to = %s
                 LIMIT 1
            ''', (int(tenant_id), number, contract_date, valid_from, valid_to))
            if cur.fetchone():
                raise ValueError('Такой договор уже есть в истории.')
            cur.execute('''
                INSERT INTO public.tenant_contracts
                    (tenant_id, contract_no, contract_date, valid_from, valid_to,
                     contract_signed, attached_in_1c, has_ds, is_legacy)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false)
            ''', (int(tenant_id), number, contract_date, valid_from, valid_to,
                  bool(contract_signed), bool(attached_in_1c), bool(has_ds)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
