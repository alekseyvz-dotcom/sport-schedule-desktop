from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from bot import db

router = Router()
log = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=3))

STATUS_TEXT = {
    "confirmed": "✅ Подтверждена",
    "rejected":  "❌ Отклонена",
}


def _compute_price_for_request(req: dict, portion_info: dict) -> str:
    """
    Вычисляет цену для заявки и возвращает строку вида
    "💰 Расч. стоимость: от 7000 ₽\n" или "".
    """
    try:
        venue_id = req["venue_id"]
        start = req["desired_start"]
        end = req["desired_end"]

        # Длительность в минутах
        start_min = start.hour * 60 + start.minute
        end_min = end.hour * 60 + end.minute
        duration = end_min - start_min
        if duration <= 0:
            return ""

        units_booked = portion_info.get("units_booked", 0)
        total_units = portion_info.get("total_units", 0)

        price = db.compute_booking_price(
            venue_id, units_booked, total_units, duration
        )

        if price is not None:
            return f"💰 Расч. стоимость: от {int(price)} ₽\n"
    except Exception:
        log.exception("Failed to compute price for request #%s", req.get("id"))

    return ""


@router.callback_query(F.data.startswith("staff:confirm:"))
async def staff_confirm(cb: CallbackQuery, bot: Bot):
    req_id = int(cb.data.split(":")[2])
    await _process(cb, bot, req_id, "confirmed")


@router.callback_query(F.data.startswith("staff:reject:"))
async def staff_reject(cb: CallbackQuery, bot: Bot):
    req_id = int(cb.data.split(":")[2])
    await _process(cb, bot, req_id, "rejected")


async def _process(cb: CallbackQuery, bot: Bot, req_id: int, new_status: str):
    req = db.get_request_by_id(req_id)
    if not req:
        await cb.answer("Заявка не найдена", show_alert=True)
        return

    if req["status"] != "new":
        msg = "Уже обработана: {}".format(req["status"])
        await cb.answer(msg, show_alert=True)
        return

    # Обновляем статус всей группы (или одной заявки)
    updated = db.update_group_status(req_id, new_status)
    updated_count = len(updated)

    # Получаем информацию о части площадки
    portion_info = db.get_request_portion_info(req_id)

    # Вычисляем цену
    price_line = _compute_price_for_request(req, portion_info)

    staff_name = cb.from_user.full_name

    # Формируем строку статуса для сообщения администратору
    status_suffix = f"\n\n{STATUS_TEXT[new_status]} — {staff_name}"
    if updated_count > 1:
        status_suffix += f"\n📋 Обработано заявок: {updated_count} (групповое бронирование)"

    await cb.message.edit_text(
        cb.message.text + status_suffix,
        reply_markup=None,
    )
    await cb.answer("Заявка #{} {}".format(req_id, STATUS_TEXT[new_status]))

    # Уведомляем пользователя
    if req.get("telegram_chat_id"):
        venue = req["venue_name"]

        # Формируем строку с частью площадки
        portion_label = portion_info.get("portion_label", "")
        unit_names = portion_info.get("unit_names", [])

        portion_line = ""
        if portion_label:
            portion_line = f"🏟 {portion_label}\n"
        if unit_names:
            units_str = ", ".join(unit_names)
            portion_line += f"📐 Зоны: {units_str}\n"

        # Если есть unit_name в самой заявке (одиночная)
        if not portion_line and req.get("unit_name"):
            venue = f"{venue} — {req['unit_name']}"

        date_str = req["desired_date"].strftime("%d.%m.%Y")
        start_str = req["desired_start"].strftime("%H:%M")
        end_str = req["desired_end"].strftime("%H:%M")

        if new_status == "confirmed":
            text = (
                f"✅ <b>Заявка #{req_id} подтверждена!</b>\n\n"
                f"📍 {venue}\n"
                f"{portion_line}"
                f"📅 {date_str}\n"
                f"🕐 {start_str}–{end_str}\n"
                f"{price_line}\n"
                f"С вами свяжутся для уточнения деталей."
            )
        else:
            text = (
                f"❌ <b>Заявка #{req_id} отклонена</b>\n\n"
                f"📍 {venue}\n"
                f"{portion_line}"
                f"📅 {date_str}\n"
                f"🕐 {start_str}–{end_str}\n\n"
                f"Попробуйте другое время: /book"
            )

        try:
            await bot.send_message(req["telegram_chat_id"], text)
        except Exception:
            log.exception("Failed to notify user %s", req["telegram_chat_id"])
