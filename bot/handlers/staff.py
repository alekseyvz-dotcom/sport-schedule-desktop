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
        msg = "\u0423\u0436\u0435 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u0430: {}".format(req["status"])
        await cb.answer(msg, show_alert=True)
        return

    db.update_request_status(req_id, new_status)

    staff_name = cb.from_user.full_name
    status_line = "\n\n{} \u2014 {}".format(STATUS_TEXT[new_status], staff_name)
    await cb.message.edit_text(
        cb.message.text + status_line,
        reply_markup=None,
    )
    await cb.answer("\u0417\u0430\u044f\u0432\u043a\u0430 #{} {}".format(req_id, STATUS_TEXT[new_status]))

    if req.get("telegram_chat_id"):
        venue = req["venue_name"]
        if req.get("unit_name"):
            venue = venue + " \u2014 " + req["unit_name"]

        date_str = req["desired_date"].strftime("%d.%m.%Y")
        start_str = req["desired_start"].strftime("%H:%M")
        end_str = req["desired_end"].strftime("%H:%M")

        if new_status == "confirmed":
            text = (
                "\u2705 <b>\u0417\u0430\u044f\u0432\u043a\u0430 #{} \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430!</b>\n\n"
                + "\ud83d\udccd " + venue + "\n"
                + "\ud83d\udcc5 " + date_str + "\n"
                + "\ud83d\udd50 " + start_str + "\u2013" + end_str + "\n\n"
                + "\u0421 \u0432\u0430\u043c\u0438 \u0441\u0432\u044f\u0436\u0443\u0442\u0441\u044f \u0434\u043b\u044f \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u044f \u0434\u0435\u0442\u0430\u043b\u0435\u0439."
            ).format(req_id)
        else:
            text = (
                "\u274c <b>\u0417\u0430\u044f\u0432\u043a\u0430 #{} \u043e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0430</b>\n\n"
                + "\ud83d\udccd " + venue + "\n"
                + "\ud83d\udcc5 " + date_str + "\n"
                + "\ud83d\udd50 " + start_str + "\u2013" + end_str + "\n\n"
                + "\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0435 \u0432\u0440\u0435\u043c\u044f: /book"
            ).format(req_id)

        try:
            await bot.send_message(req["telegram_chat_id"], text)
        except Exception:
            log.exception("Failed to notify user %s", req["telegram_chat_id"])
