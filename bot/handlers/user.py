from __future__ import annotations

import logging
from datetime import date, timedelta, time

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove,
)

from bot.states import BookingFlow
from bot.config import settings
from bot import db

router = Router()
log = logging.getLogger(__name__)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def org_keyboard(orgs):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=o["name"], callback_data=f"org:{o['id']}")]
        for o in orgs
    ])


def resource_keyboard(resources):
    buttons = [
        [InlineKeyboardButton(
            text=r["name"],
            callback_data=f"res:{r['venue_id']}:{r['venue_unit_id'] or 0}",
        )]
        for r in resources
    ]
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back:org")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def date_keyboard():
    today = date.today()
    buttons = []
    row = []
    for i in range(settings.MAX_DAYS_AHEAD):
        d = today + timedelta(days=i)
        label = "\u0421\u0435\u0433\u043e\u0434\u043d\u044f" if i == 0 else f"{d:%d.%m} ({WEEKDAYS[d.weekday()]})"
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"date:{d.isoformat()}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back:resource")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def slots_keyboard(slots, mode="start"):
    free_slots = [s for s in slots if s["free"]]
    if not free_slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f \u0414\u0440\u0443\u0433\u0430\u044f \u0434\u0430\u0442\u0430", callback_data="back:date")]
        ])

    cb_prefix = "sstart" if mode == "start" else "send"
    buttons = []
    row = []
    for s in free_slots:
        label = s["start"].strftime("%H:%M") if hasattr(s["start"], "strftime") else s["start"]
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"{cb_prefix}:{label}"
        ))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434",
        callback_data="back:date" if mode == "start" else "back:slot_start",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2705 \u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c", callback_data="confirm:yes"),
            InlineKeyboardButton(text="\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="confirm:no"),
        ],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e", callback_data="restart")],
    ])


def skip_keyboard(field):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u041f\u0440\u043e\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u25b6\ufe0f", callback_data=f"skip:{field}")]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "\ud83c\udfdf <b>\u0411\u0440\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043f\u043b\u043e\u0449\u0430\u0434\u043e\u043a</b>\n\n"
        "\u042f \u043f\u043e\u043c\u043e\u0433\u0443 \u0437\u0430\u0431\u0440\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u043f\u043e\u0440\u0442\u0438\u0432\u043d\u0443\u044e \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0443.\n\n"
        "\ud83d\udccc \u041a\u043e\u043c\u0430\u043d\u0434\u044b:\n"
        "/book \u2014 \u0437\u0430\u0431\u0440\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u0442\u044c\n"
        "/my \u2014 \u043c\u043e\u0438 \u0437\u0430\u044f\u0432\u043a\u0438\n"
        "/help \u2014 \u043f\u043e\u043c\u043e\u0449\u044c",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "\ud83d\udcd6 <b>\u041a\u0430\u043a \u044d\u0442\u043e \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442:</b>\n\n"
        "1\ufe0f\u20e3 \u041d\u0430\u0436\u043c\u0438\u0442\u0435 /book\n"
        "2\ufe0f\u20e3 \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0443\u0447\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435 \u0438 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0443\n"
        "3\ufe0f\u20e3 \u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0430\u0442\u0443 \u0438 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u043e\u0435 \u0432\u0440\u0435\u043c\u044f\n"
        "4\ufe0f\u20e3 \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435\n"
        "5\ufe0f\u20e3 \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u0437\u0430\u044f\u0432\u043a\u0443\n\n"
        "\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a \u043f\u043e\u043b\u0443\u0447\u0438\u0442 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435 \u0438 \u0441\u0432\u044f\u0436\u0435\u0442\u0441\u044f \u0441 \u0432\u0430\u043c\u0438.\n"
        "\u0421\u0442\u0430\u0442\u0443\u0441 \u0437\u0430\u044f\u0432\u043a\u0438 \u043c\u043e\u0436\u043d\u043e \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c: /my"
    )


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    await state.clear()
    orgs = db.load_orgs()
    if not orgs:
        await message.answer("\ud83d\ude14 \u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u0443\u0447\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0439.")
        return

    if len(orgs) == 1:
        await state.update_data(org_id=orgs[0]["id"], org_name=orgs[0]["name"])
        resources = db.load_resources(orgs[0]["id"])
        if not resources:
            await message.answer("\ud83d\ude14 \u041d\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u043f\u043b\u043e\u0449\u0430\u0434\u043e\u043a.")
            return
        await state.set_state(BookingFlow.choose_resource)
        await message.answer(
            f"\ud83c\udfe2 <b>{orgs[0]['name']}</b>\n\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0443:",
            reply_markup=resource_keyboard(resources),
        )
        return

    await state.set_state(BookingFlow.choose_org)
    await message.answer("\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0443\u0447\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435:", reply_markup=org_keyboard(orgs))


@router.message(Command("my"))
async def cmd_my(message: Message):
    rows = db.get_user_requests(message.from_user.id)
    if not rows:
        await message.answer("\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0437\u0430\u044f\u0432\u043e\u043a. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 /book")
        return

    status_emoji = {
        "new": "\ud83c\udd95", "confirmed": "\u2705",
        "rejected": "\u274c", "cancelled": "\ud83d\udeab",
    }

    lines = ["\ud83d\udccb <b>\u0412\u0430\u0448\u0438 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0437\u0430\u044f\u0432\u043a\u0438:</b>\n"]
    for r in rows:
        venue = r["venue_name"]
        if r["unit_name"]:
            venue += f" \u2014 {r['unit_name']}"
        emoji = status_emoji.get(r["status"], "\u2753")
        comment = ""
        if r["staff_comment"]:
            comment = f"\n   \ud83d\udcac {r['staff_comment']}"
        lines.append(
            f"{emoji} <b>#{r['id']}</b>  {r['desired_date']:%d.%m.%Y} "
            f"{r['desired_start']:%H:%M}\u2013{r['desired_end']:%H:%M}\n"
            f"   \ud83d\udccd {venue}{comment}"
        )

    await message.answer("\n".join(lines))


@router.callback_query(BookingFlow.choose_org, F.data.startswith("org:"))
async def on_org(cb: CallbackQuery, state: FSMContext):
    org_id = int(cb.data.split(":")[1])
    org = db.get_org(org_id)
    if not org:
        await cb.answer("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e", show_alert=True)
        return

    await state.update_data(org_id=org_id, org_name=org["name"])
    resources = db.load_resources(org_id)
    if not resources:
        await cb.answer("\u041d\u0435\u0442 \u043f\u043b\u043e\u0449\u0430\u0434\u043e\u043a", show_alert=True)
        return

    await state.set_state(BookingFlow.choose_resource)
    await cb.message.edit_text(
        f"\ud83c\udfe2 <b>{org['name']}</b>\n\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0443:",
        reply_markup=resource_keyboard(resources),
    )
    await cb.answer()


@router.callback_query(BookingFlow.choose_resource, F.data.startswith("res:"))
async def on_resource(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    venue_id = int(parts[1])
    venue_unit_id = int(parts[2]) if parts[2] != "0" else None

    data = await state.get_data()
    resources = db.load_resources(data["org_id"])
    resource = next(
        (r for r in resources
         if r["venue_id"] == venue_id
         and r.get("venue_unit_id") == venue_unit_id),
        None,
    )
    if not resource:
        await cb.answer("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e", show_alert=True)
        return

    await state.update_data(
        venue_id=venue_id,
        venue_unit_id=venue_unit_id,
        resource_name=resource["name"],
    )
    await state.set_state(BookingFlow.choose_date)
    await cb.message.edit_text(
        f"\ud83d\udccd <b>{resource['name']}</b>\n\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0430\u0442\u0443:",
        reply_markup=date_keyboard(),
    )
    await cb.answer()


@router.callback_query(BookingFlow.choose_date, F.data.startswith("date:"))
async def on_date(cb: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(cb.data.split(":")[1])
    data = await state.get_data()

    if not db.is_venue_available(data["venue_id"], data["org_id"], d):
        await cb.answer("\u274c \u041f\u043b\u043e\u0449\u0430\u0434\u043a\u0430 \u0437\u0430\u043a\u0440\u044b\u0442\u0430 \u0432 \u044d\u0442\u043e\u0442 \u0434\u0435\u043d\u044c", show_alert=True)
        return

    slots = db.compute_free_slots(
        data["venue_id"], data.get("venue_unit_id"), data["org_id"], d
    )
    free_count = sum(1 for s in slots if s["free"])

    if free_count == 0:
        await cb.answer("\ud83d\ude14 \u041d\u0435\u0442 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0445 \u0441\u043b\u043e\u0442\u043e\u0432", show_alert=True)
        return

    date_label = f"{d:%d.%m.%Y} ({WEEKDAYS[d.weekday()]})"
    await state.update_data(
        desired_date=d.isoformat(),
        date_label=date_label,
        slots_cache=[
            {"start": s["start"].strftime("%H:%M"),
             "end": s["end"].strftime("%H:%M"),
             "free": s["free"]}
            for s in slots
        ],
    )
    await state.set_state(BookingFlow.choose_slot_start)
    await cb.message.edit_text(
        f"\ud83d\udccd {data['resource_name']}\n"
        f"\ud83d\udcc5 {date_label}\n\n"
        f"\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0445 \u0441\u043b\u043e\u0442\u043e\u0432: {free_count}\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 <b>\u043d\u0430\u0447\u0430\u043b\u043e</b>:",
        reply_markup=slots_keyboard(slots, mode="start"),
    )
    await cb.answer()


@router.callback_query(BookingFlow.choose_slot_start, F.data.startswith("sstart:"))
async def on_slot_start(cb: CallbackQuery, state: FSMContext):
    start_str = cb.data.split(":")[1]
    data = await state.get_data()
    all_slots = data["slots_cache"]

    start_idx = next(
        (i for i, s in enumerate(all_slots) if s["start"] == start_str), 0
    )

    end_options = []
    for i in range(start_idx, min(start_idx + settings.MAX_BOOKING_SLOTS, len(all_slots))):
        if not all_slots[i]["free"]:
            break
        end_options.append(all_slots[i])

    if not end_options:
        await cb.answer("\u041d\u0435\u0442 \u0432\u0430\u0440\u0438\u0430\u043d\u0442\u043e\u0432", show_alert=True)
        return

    buttons = []
    row = []
    for s in end_options:
        row.append(InlineKeyboardButton(
            text=f"\u0434\u043e {s['end']}", callback_data=f"send:{s['end']}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="back:slot_start")])

    await state.update_data(slot_start=start_str)
    await state.set_state(BookingFlow.choose_slot_end)
    await cb.message.edit_text(
        f"\ud83d\udccd {data['resource_name']}\n"
        f"\ud83d\udcc5 {data['date_label']}\n"
        f"\ud83d\udd50 \u041d\u0430\u0447\u0430\u043b\u043e: <b>{start_str}</b>\n\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 <b>\u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u0435</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await cb.answer()


@router.callback_query(BookingFlow.choose_slot_end, F.data.startswith("send:"))
async def on_slot_end(cb: CallbackQuery, state: FSMContext):
    end_str = cb.data.split(":")[1]
    data = await state.get_data()

    await state.update_data(slot_end=end_str)
    await state.set_state(BookingFlow.enter_name)
    await cb.message.edit_text(
        f"\ud83d\udccd {data['resource_name']}\n"
        f"\ud83d\udcc5 {data['date_label']}\n"
        f"\ud83d\udd50 {data['slot_start']} \u2013 {end_str}\n\n"
        "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 <b>\u0432\u0430\u0448\u0435 \u0438\u043c\u044f</b> (\u0424\u0418\u041e):",
    )
    await cb.answer()


@router.message(BookingFlow.enter_name)
async def on_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u043e\u0435 \u0438\u043c\u044f (\u043c\u0438\u043d\u0438\u043c\u0443\u043c 2 \u0441\u0438\u043c\u0432\u043e\u043b\u0430):")
        return

    await state.update_data(contact_name=name)
    await state.set_state(BookingFlow.enter_phone)
    await message.answer(
        f"\ud83d\udc64 {name}\n\n\u0412\u0432\u0435\u0434\u0438\u0442\u0435 <b>\u043d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430</b> \u0434\u043b\u044f \u0441\u0432\u044f\u0437\u0438:",
        reply_markup=skip_keyboard("phone"),
    )


@router.callback_query(BookingFlow.enter_phone, F.data == "skip:phone")
async def skip_phone(cb: CallbackQuery, state: FSMContext):
    await state.update_data(contact_phone=None)
    await state.set_state(BookingFlow.enter_comment)
    await cb.message.edit_text(
        "\u0425\u043e\u0442\u0438\u0442\u0435 \u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c <b>\u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439</b>?\n(\u0446\u0435\u043b\u044c \u0430\u0440\u0435\u043d\u0434\u044b, \u043f\u043e\u0436\u0435\u043b\u0430\u043d\u0438\u044f)",
        reply_markup=skip_keyboard("comment"),
    )
    await cb.answer()


@router.message(BookingFlow.enter_phone)
async def on_phone(message: Message, state: FSMContext):
    await state.update_data(contact_phone=message.text.strip())
    await state.set_state(BookingFlow.enter_comment)
    await message.answer(
        "\u0425\u043e\u0442\u0438\u0442\u0435 \u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c <b>\u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439</b>?\n(\u0446\u0435\u043b\u044c \u0430\u0440\u0435\u043d\u0434\u044b, \u043f\u043e\u0436\u0435\u043b\u0430\u043d\u0438\u044f)",
        reply_markup=skip_keyboard("comment"),
    )


@router.callback_query(BookingFlow.enter_comment, F.data == "skip:comment")
async def skip_comment(cb: CallbackQuery, state: FSMContext):
    await state.update_data(message=None)
    await _show_confirm(cb.message, state, edit=True)
    await cb.answer()


@router.message(BookingFlow.enter_comment)
async def on_comment(message: Message, state: FSMContext):
    await state.update_data(message=message.text.strip())
    await _show_confirm(message, state, edit=False)


async def _show_confirm(msg, state, edit):
    data = await state.get_data()
    await state.set_state(BookingFlow.confirm)

    text = (
        "\ud83d\udccb <b>\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0437\u0430\u044f\u0432\u043a\u0443:</b>\n\n"
        f"\ud83c\udfe2 {data.get('org_name', '')}\n"
        f"\ud83d\udccd {data['resource_name']}\n"
        f"\ud83d\udcc5 {data['date_label']}\n"
        f"\ud83d\udd50 {data['slot_start']} \u2013 {data['slot_end']}\n\n"
        f"\ud83d\udc64 {data['contact_name']}\n"
        f"\ud83d\udcde {data.get('contact_phone') or '\u2014'}\n"
        f"\ud83d\udcac {data.get('message') or '\u2014'}\n\n"
        "\u0412\u0441\u0451 \u0432\u0435\u0440\u043d\u043e?"
    )

    if edit:
        await msg.edit_text(text, reply_markup=confirm_keyboard())
    else:
        await msg.answer(text, reply_markup=confirm_keyboard())


@router.callback_query(BookingFlow.confirm, F.data == "confirm:yes")
async def on_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    d = date.fromisoformat(data["desired_date"])
    sh, sm = map(int, data["slot_start"].split(":"))
    eh, em = map(int, data["slot_end"].split(":"))

    req_data = {
        "org_id":           data["org_id"],
        "venue_id":         data["venue_id"],
        "venue_unit_id":    data.get("venue_unit_id"),
        "desired_date":     d,
        "desired_start":    time(sh, sm),
        "desired_end":      time(eh, em),
        "contact_name":     data["contact_name"],
        "contact_phone":    data.get("contact_phone"),
        "contact_email":    None,
        "telegram_user_id": cb.from_user.id,
        "telegram_chat_id": cb.message.chat.id,
        "message":          data.get("message"),
    }

    try:
        req_id = db.save_request(req_data)
    except Exception:
        log.exception("Failed to save request")
        await cb.message.edit_text(
            "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u044f. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435.\n/book"
        )
        await state.clear()
        await cb.answer()
        return

    await cb.message.edit_text(
        f"\u2705 <b>\u0417\u0430\u044f\u0432\u043a\u0430 #{req_id} \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430!</b>\n\n"
        f"\ud83d\udccd {data['resource_name']}\n"
        f"\ud83d\udcc5 {data['date_label']}\n"
        f"\ud83d\udd50 {data['slot_start']} \u2013 {data['slot_end']}\n\n"
        "\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a \u0441\u0432\u044f\u0436\u0435\u0442\u0441\u044f \u0441 \u0432\u0430\u043c\u0438.\n"
        "\u0421\u0442\u0430\u0442\u0443\u0441 \u0437\u0430\u044f\u0432\u043a\u0438: /my"
    )
    await state.clear()
    await cb.answer()

    staff_ids = db.get_staff_chat_ids(data["org_id"])
    if staff_ids:
        staff_text = (
            f"\ud83d\udccb <b>\u041d\u043e\u0432\u0430\u044f \u0437\u0430\u044f\u0432\u043a\u0430 #{req_id}</b>\n\n"
            f"\ud83c\udfe2 {data.get('org_name', '')}\n"
            f"\ud83d\udccd {data['resource_name']}\n"
            f"\ud83d\udcc5 {data['date_label']}\n"
            f"\ud83d\udd50 {data['slot_start']} \u2013 {data['slot_end']}\n\n"
            f"\ud83d\udc64 {data['contact_name']}\n"
            f"\ud83d\udcde {data.get('contact_phone') or '\u2014'}\n"
            f"\ud83d\udcac {data.get('message') or '\u2014'}\n"
            f"\ud83c\udd94 @{cb.from_user.username or '\u2014'}"
        )
        staff_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c",
                    callback_data=f"staff:confirm:{req_id}",
                ),
                InlineKeyboardButton(
                    text="\u274c \u041e\u0442\u043a\u043b\u043e\u043d\u0438\u0442\u044c",
                    callback_data=f"staff:reject:{req_id}",
                ),
            ],
        ])
        for chat_id in staff_ids:
            try:
                await bot.send_message(chat_id, staff_text, reply_markup=staff_kb)
            except Exception:
                log.exception("Failed to notify staff %s", chat_id)


@router.callback_query(BookingFlow.confirm, F.data == "confirm:no")
async def on_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("\ud83d\udeab \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e.\n\n/book \u2014 \u043d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043d\u043e\u0432\u043e")
    await cb.answer()


@router.callback_query(F.data == "restart")
async def on_restart(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    orgs = db.load_orgs()
    if len(orgs) == 1:
        await state.update_data(org_id=orgs[0]["id"], org_name=orgs[0]["name"])
        resources = db.load_resources(orgs[0]["id"])
        await state.set_state(BookingFlow.choose_resource)
        await cb.message.edit_text(
            f"\ud83c\udfe2 <b>{orgs[0]['name']}</b>\n\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0443:",
            reply_markup=resource_keyboard(resources),
        )
    elif orgs:
        await state.set_state(BookingFlow.choose_org)
        await cb.message.edit_text(
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0443\u0447\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435:", reply_markup=org_keyboard(orgs)
        )
    else:
        await cb.message.edit_text("\ud83d\ude14 \u041d\u0435\u0442 \u0443\u0447\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0439.")
    await cb.answer()


@router.callback_query(F.data == "back:org")
async def back_org(cb: CallbackQuery, state: FSMContext):
    orgs = db.load_orgs()
    await state.set_state(BookingFlow.choose_org)
    await cb.message.edit_text(
        "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0443\u0447\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435:", reply_markup=org_keyboard(orgs)
    )
    await cb.answer()


@router.callback_query(F.data == "back:resource")
async def back_resource(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    resources = db.load_resources(data["org_id"])
    await state.set_state(BookingFlow.choose_resource)
    await cb.message.edit_text(
        f"\ud83c\udfe2 <b>{data.get('org_name', '')}</b>\n\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0443:",
        reply_markup=resource_keyboard(resources),
    )
    await cb.answer()


@router.callback_query(F.data == "back:date")
async def back_date(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BookingFlow.choose_date)
    await cb.message.edit_text(
        f"\ud83d\udccd <b>{data['resource_name']}</b>\n\n\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0430\u0442\u0443:",
        reply_markup=date_keyboard(),
    )
    await cb.answer()


@router.callback_query(F.data == "back:slot_start")
async def back_slot_start(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    slots = data.get("slots_cache", [])
    await state.set_state(BookingFlow.choose_slot_start)
    await cb.message.edit_text(
        f"\ud83d\udccd {data['resource_name']}\n"
        f"\ud83d\udcc5 {data['date_label']}\n\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 <b>\u043d\u0430\u0447\u0430\u043b\u043e</b>:",
        reply_markup=slots_keyboard(slots, mode="start"),
    )
    await cb.answer()
