from __future__ import annotations

import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from bot import db

router = Router()
log = logging.getLogger(__name__)

STATUS_TEXT = {
    "confirmed": "\u2705 \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430",
    "rejected":  "\u274c \u041e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0430",
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
        await cb.answer("\u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430", show_alert=True)
        return

    if req["status"] != "new":
        await cb.answer(f"\u0423\u0436\u0435 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u0430: {req['status']}", show_alert=True)
        return

    db.update_request_status(req_id, new_status)

    staff_name = cb.from_user.full_name
    await cb.message.edit_text(
        cb.message.text + f"\n\n{STATUS_TEXT[new_status]} \u2014 {staff_name}",
        reply_markup=None,
    )
    await cb.answer(f"\u0417\u0430\u044f\u0432\u043a\u0430 #{req_id} {STATUS_TEXT[new_status]}")

    if req.get("telegram_chat_id"):
        venue = req["venue_name"]
        if req.get("unit_name"):
            venue += f" \u2014 {req['unit_name']}"

        if new_status == "confirmed":
            text = (
                f"\u2705 <b>\u0417\u0430\u044f\u0432\u043a\u0430 #{req_id} \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430!</b>\n\n"
                f"\ud83d\udccd {venue}\n"
                f"\ud83d\udcc5 {req['desired_date']:%d.%m.%Y}\n"
                f"\ud83d\udd50 {req['desired_start']:%H:%M}\u2013{req['desired_end']:%H:%M}\n\n"
                "\u0421 \u0432\u0430\u043c\u0438 \u0441\u0432\u044f\u0436\u0443\u0442\u0441\u044f \u0434\u043b\u044f \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u044f \u0434\u0435\u0442\u0430\u043b\u0435\u0439."
            )
        else:
            text = (
                f"\u274c <b>\u0417\u0430\u044f\u0432\u043a\u0430 #{req_id} \u043e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0430</b>\n\n"
                f"\ud83d\udccd {venue}\n"
                f"\ud83d\udcc5 {req['desired_date']:%d.%m.%Y}\n"
                f"\ud83d\udd50 {req['desired_start']:%H:%M}\u2013{req['desired_end']:%H:%M}\n\n"
                "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0435 \u0432\u0440\u0435\u043c\u044f: /book"
            )

        try:
            await bot.send_message(req["telegram_chat_id"], text)
        except Exception:
            log.exception("Failed to notify user %s", req["telegram_chat_id"])
