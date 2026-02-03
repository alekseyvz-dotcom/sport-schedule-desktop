from __future__ import annotations

from typing import List, Tuple

from app.db import get_conn, put_conn

# схемы: (code, name, sort_order)
UNITS_1 = [("MAIN", "Основная зона", 10)]
UNITS_2 = [("H1", "1/2 #1", 10), ("H2", "1/2 #2", 20)]
UNITS_4 = [("Q1", "1/4 #1", 10), ("Q2", "1/4 #2", 20), ("Q3", "1/4 #3", 30), ("Q4", "1/4 #4", 40)]


def detect_units_scheme(venue_id: int) -> int:
    """
    Возвращает схему:
      0 - нет (все зоны выключены)
      1 - одна зона (MAIN)
      2 - две зоны (H1,H2)
      4 - четыре зоны (Q1..Q4)
    """
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code FROM public.venue_units WHERE venue_id=%s AND is_active=true ORDER BY sort_order, code",
                (int(venue_id),),
            )
            codes = [str(r[0]) for r in cur.fetchall()]
    finally:
        if conn:
            put_conn(conn)

    if not codes:
        return 0
    if set(codes) == {"MAIN"}:
        return 1
    if set(codes) == {"H1", "H2"}:
        return 2
    if set(codes) == {"Q1", "Q2", "Q3", "Q4"}:
        return 4
    # если вручную сделали другое — считаем как "нестандартно"
    return 0


def apply_units_scheme(venue_id: int, scheme: int) -> None:
    """
    Применяет схему зон:
      0 - деактивировать все unit'ы
      1 - создать/активировать MAIN и деактивировать остальные
      2 - создать/активировать H1/H2 и деактивировать остальные
      4 - создать/активировать Q1..Q4 и деактивировать остальные
    """
    scheme = int(scheme)
    if scheme not in (0, 1, 2, 4):
        raise ValueError("scheme должен быть 0, 1, 2 или 4")

    desired: List[Tuple[str, str, int]]
    if scheme == 0:
        desired = []
    elif scheme == 1:
        desired = UNITS_1
    elif scheme == 2:
        desired = UNITS_2
    else:
        desired = UNITS_4

    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.venue_units SET is_active=false WHERE venue_id=%s",
                    (int(venue_id),),
                )

                for code, name, sort_order in desired:
                    cur.execute(
                        """
                        INSERT INTO public.venue_units(venue_id, code, name, sort_order, is_active)
                        VALUES (%s, %s, %s, %s, true)
                        ON CONFLICT (venue_id, code)
                        DO UPDATE SET name=EXCLUDED.name, sort_order=EXCLUDED.sort_order, is_active=true
                        """,
                        (int(venue_id), code, name, int(sort_order)),
                    )
    finally:
        if conn:
            put_conn(conn)
