from __future__ import annotations

import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from bot import db

router = Router()
log = logging.getLogger(__name__)

STATUS_TEXT = {
    "confirmed": "✅ Подтверждена",
    "rejected":  "❌ Отклонена",
}


@router.callback_query(F.data.startswith("staff:confirm:"))
async def staff_confirm(cb: CallbackQuery, bot: Bot):
    req_id = int(cb.data.split(":")[2])
    await _process(cb, bot, req_id, "confirmed")


@router.callback_query(F.data.startswith("staff:reject:"))
async def staff_reject(cb: CallbackQuery, bot: Bot):
    req_id = int(cb.data.split(":")[2])
    await _process(cb, bot, req_id, "rejected")


async def _process(cb, bot, req_id, new_status):
    req = db.get_request_by_id(req_id)
    if not req:
        await cb.answer("Заявка не найдена", show_alert=True)
        return

    if req["status"] != "new":
        msg = "Уже обработана: {}".format(req["status"])
        await cb.answer(msg, show_alert=True)
        return

    db.update_request_status(req_id, new_status)

    staff_name = cb.from_user.full_name
    status_line = "\n\n{} — {}".format(STATUS_TEXT[new_status], staff_name)
    await cb.message.edit_text(
        cb.message.text + status_line,
        reply_markup=None,
    )
    await cb.answer("Заявка #{} {}".format(req_id, STATUS_TEXT[new_status]))

    if req.get("telegram_chat_id"):
        venue = req["venue_name"]
        if req.get("unit_name"):
            venue = venue + " — " + req["unit_name"]

        date_str = req["desired_date"].strftime("%d.%m.%Y")
        start_str = req["desired_start"].strftime("%H:%M")
        end_str = req["desired_end"].strftime("%H:%M")

        if new_status == "confirmed":
            text = (
                "✅ <b>Заявка #{} подтверждена!</b>\n\n"
                "📍 {}\n"
                "📅 {}\n"
                "🕐 {}–{}\n\n"
                "С вами свяжутся для уточнения деталей."
            ).format(req_id, venue, date_str, start_str, end_str)
        else:
            text = (
                "❌ <b>Заявка #{} отклонена</b>\n\n"
                "📍 {}\n"
                "📅 {}\n"
                "🕐 {}–{}\n\n"
                "Попробуйте другое время: /book"
            ).format(req_id, venue, date_str, start_str, end_str)

        try:
            await bot.send_message(req["telegram_chat_id"], text)
        except Exception:
            log.exception("Failed to notify user %s", req["telegram_chat_id"])
