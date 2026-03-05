from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from psycopg2.extras import RealDictCursor

from app.db import get_conn, put_conn


@dataclass
class VenuePrices:
    venue_id: int
    price_q_60: Optional[Decimal] = None
    price_q_90: Optional[Decimal] = None
    price_h_60: Optional[Decimal] = None
    price_h_90: Optional[Decimal] = None
    price_f_60: Optional[Decimal] = None
    price_f_90: Optional[Decimal] = None


def get_venue_prices(venue_id: int) -> VenuePrices:
    """Возвращает цены площадки. Если записи нет — возвращает пустой объект."""
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT price_q_60, price_q_90,
                       price_h_60, price_h_90,
                       price_f_60, price_f_90
                FROM public.venue_prices
                WHERE venue_id = %s AND is_active = true
                """,
                (int(venue_id),),
            )
            row = cur.fetchone()
        if not row:
            return VenuePrices(venue_id=venue_id)
        return VenuePrices(
            venue_id=venue_id,
            price_q_60=row["price_q_60"],
            price_q_90=row["price_q_90"],
            price_h_60=row["price_h_60"],
            price_h_90=row["price_h_90"],
            price_f_60=row["price_f_60"],
            price_f_90=row["price_f_90"],
        )
    finally:
        if conn:
            put_conn(conn)


def save_venue_prices(venue_id: int, prices: VenuePrices) -> None:
    """Сохраняет (upsert) цены площадки."""
    conn = None
    try:
        conn = get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.venue_prices
                        (venue_id, price_q_60, price_q_90,
                         price_h_60, price_h_90,
                         price_f_60, price_f_90,
                         is_active, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, true, now())
                    ON CONFLICT (venue_id) WHERE (is_active = true)
                    DO UPDATE SET
                        price_q_60 = EXCLUDED.price_q_60,
                        price_q_90 = EXCLUDED.price_q_90,
                        price_h_60 = EXCLUDED.price_h_60,
                        price_h_90 = EXCLUDED.price_h_90,
                        price_f_60 = EXCLUDED.price_f_60,
                        price_f_90 = EXCLUDED.price_f_90,
                        updated_at = now()
                    """,
                    (
                        int(venue_id),
                        prices.price_q_60,
                        prices.price_q_90,
                        prices.price_h_60,
                        prices.price_h_90,
                        prices.price_f_60,
                        prices.price_f_90,
                    ),
                )
    finally:
        if conn:
            put_conn(conn)


def compute_price(
    venue_id: int,
    units_needed: int,
    total_units: int,
    duration_minutes: int,
) -> Optional[Decimal]:
    """
    Вычисляет цену бронирования.

    units_needed: сколько зон бронируется (1, 2, 4)
    total_units: сколько зон у площадки (0, 1, 2, 4)
    duration_minutes: 60 или 90

    Возвращает цену или None если цена не задана.
    """
    prices = get_venue_prices(venue_id)

    # Определяем тип части
    if total_units == 0 or units_needed >= total_units:
        portion = "f"  # full
    else:
        fraction = units_needed / total_units
        if abs(fraction - 0.25) < 0.01:
            portion = "q"  # quarter
        elif abs(fraction - 0.5) < 0.01:
            portion = "h"  # half
        else:
            portion = "f"  # fallback to full

    # Определяем длительность
    if duration_minutes <= 60:
        dur = "60"
    elif duration_minutes <= 90:
        dur = "90"
    else:
        # Для 120 мин — считаем как 2×60
        price_60 = getattr(prices, f"price_{portion}_60", None)
        if price_60 is not None:
            return price_60 * 2
        return None

    field = f"price_{portion}_{dur}"
    return getattr(prices, field, None)
