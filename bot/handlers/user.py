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

# Варианты длительности бронирования (в минутах)
DURATION_OPTIONS = [30, 60, 90, 120, 150, 180]


def org_keyboard(orgs):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=o["name"], callback_data="org:{}".format(o["id"]))]
        for o in orgs
    ])


def resource_keyboard(resources):
    buttons = [
        [InlineKeyboardButton(
            text=r["name"],
            callback_data="res:{}".format(r["venue_id"]),
        )]
        for r in resources
    ]
    buttons.append([InlineKeyboardButton(text="< Назад", callback_data="back:org")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def date_keyboard():
    today = date.today()
    buttons = []
    row = []
    for i in range(settings.MAX_DAYS_AHEAD):
        d = today + timedelta(days=i)
        if i == 0:
            label = "Сегодня"
        else:
            label = "{} ({})".format(d.strftime("%d.%m"), WEEKDAYS[d.weekday()])
        row.append(InlineKeyboardButton(
            text=label, callback_data="date_{}".format(d.isoformat())
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="< Назад", callback_data="back:resource")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def slots_keyboard(slots):
    """Клавиатура выбора времени НАЧАЛА"""
    free_slots = [s for s in slots if s["free"]]
    if not free_slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="< Другая дата", callback_data="back:date")]
        ])

    buttons = []
    row = []
    for s in free_slots:
        if hasattr(s["start"], "strftime"):
            label = s["start"].strftime("%H-%M")
        else:
            label = s["start"].replace(":", "-")
        row.append(InlineKeyboardButton(
            text=label.replace("-", ":"),
            callback_data="sstart_{}".format(label),
        ))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="< Назад", callback_data="back:date")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def duration_keyboard(available_minutes: list[int]):
    """Клавиатура выбора длительности"""
    buttons = []
    row = []
    for mins in available_minutes:
        if mins < 60:
            label = "{} мин".format(mins)
        elif mins % 60 == 0:
            label = "{} ч".format(mins // 60)
        else:
            label = "{}:{:02d}".format(mins // 60, mins % 60)
        row.append(InlineKeyboardButton(
            text=label,
            callback_data="dur_{}".format(mins),
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="< Назад", callback_data="back:slot_start")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отправить", callback_data="confirm:yes"),
            InlineKeyboardButton(text="Отмена", callback_data="confirm:no"),
        ],
        [InlineKeyboardButton(text="< Начать заново", callback_data="restart")],
    ])


def skip_keyboard(field):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить >", callback_data="skip:{}".format(field))]
    ])


# ---------- /start ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Бронирование площадок\n\n"
        "Я помогу забронировать спортивную площадку.\n\n"
        "Команды:\n"
        "/book - забронировать\n"
        "/my - мои заявки\n"
        "/help - помощь"
    )
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


# ---------- /help ----------
@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>Как это работает:</b>\n\n"
        "1. Нажмите /book\n"
        "2. Выберите учреждение и площадку\n"
        "3. Выберите дату и свободное время\n"
        "4. Выберите длительность\n"
        "5. Введите контактные данные\n"
        "6. Подтвердите заявку\n\n"
        "Сотрудник получит уведомление и свяжется с вами.\n"
        "Статус заявки: /my"
    )
    await message.answer(text)


# ---------- /book ----------
@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    await state.clear()
    orgs = db.load_orgs()
    if not orgs:
        await message.answer("Нет доступных учреждений.")
        return

    if len(orgs) == 1:
        org = orgs[0]
        await state.update_data(org_id=org["id"], org_name=org["name"])
        resources = db.load_resources(org["id"])
        if not resources:
            await message.answer("Нет доступных площадок.")
            return
        await state.set_state(BookingFlow.choose_resource)
        text = "<b>{}</b>\n\nВыберите площадку:".format(org["name"])
        await message.answer(text, reply_markup=resource_keyboard(resources))
        return

    await state.set_state(BookingFlow.choose_org)
    await message.answer("Выберите учреждение:", reply_markup=org_keyboard(orgs))


# ---------- /my ----------
@router.message(Command("my"))
async def cmd_my(message: Message):
    rows = db.get_user_requests(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет заявок. Нажмите /book")
        return

    status_emoji = {
        "new": "NEW",
        "confirmed": "OK",
        "rejected": "X",
        "cancelled": "---",
    }

    lines = ["<b>Ваши последние заявки:</b>\n"]
    for r in rows:
        venue = r["venue_name"]
        emoji = status_emoji.get(r["status"], "?")
        comment = ""
        if r["staff_comment"]:
            comment = "\n   Комментарий: " + r["staff_comment"]
        date_str = r["desired_date"].strftime("%d.%m.%Y")
        start_str = r["desired_start"].strftime("%H:%M")
        end_str = r["desired_end"].strftime("%H:%M")
        line = "[{}] <b>#{}</b>  {} {}--{}\n   {}{}".format(
            emoji, r["id"], date_str, start_str, end_str, venue, comment
        )
        lines.append(line)

    await message.answer("\n".join(lines))


# ---------- choose org ----------
@router.callback_query(BookingFlow.choose_org, F.data.startswith("org:"))
async def on_org(cb: CallbackQuery, state: FSMContext):
    org_id = int(cb.data.split(":")[1])
    org = db.get_org(org_id)
    if not org:
        await cb.answer("Не найдено", show_alert=True)
        return

    await state.update_data(org_id=org_id, org_name=org["name"])
    resources = db.load_resources(org_id)
    if not resources:
        await cb.answer("Нет площадок", show_alert=True)
        return

    await state.set_state(BookingFlow.choose_resource)
    text = "<b>{}</b>\n\nВыберите площадку:".format(org["name"])
    await cb.message.edit_text(text, reply_markup=resource_keyboard(resources))
    await cb.answer()


# ---------- choose resource ----------
@router.callback_query(BookingFlow.choose_resource, F.data.startswith("res:"))
async def on_resource(cb: CallbackQuery, state: FSMContext):
    venue_id = int(cb.data.split(":")[1])

    data = await state.get_data()
    resources = db.load_resources(data["org_id"])
    resource = next(
        (r for r in resources if r["venue_id"] == venue_id),
        None,
    )
    if not resource:
        await cb.answer("Не найдено", show_alert=True)
        return

    await state.update_data(
        venue_id=venue_id,
        venue_unit_id=None,
        resource_name=resource["name"],
    )
    await state.set_state(BookingFlow.choose_date)
    text = "<b>{}</b>\n\nВыберите дату:".format(resource["name"])
    await cb.message.edit_text(text, reply_markup=date_keyboard())
    await cb.answer()


# ---------- choose date ----------
@router.callback_query(BookingFlow.choose_date, F.data.startswith("date_"))
async def on_date(cb: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(cb.data.replace("date_", ""))
    data = await state.get_data()

    if not db.is_venue_available(data["venue_id"], data["org_id"], d):
        await cb.answer("Площадка закрыта в этот день", show_alert=True)
        return

    slots = db.compute_free_slots(
        data["venue_id"], data.get("venue_unit_id"), data["org_id"], d
    )
    free_count = sum(1 for s in slots if s["free"])

    if free_count == 0:
        await cb.answer("Нет свободных слотов", show_alert=True)
        return

    date_label = "{} ({})".format(d.strftime("%d.%m.%Y"), WEEKDAYS[d.weekday()])
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
    text = "{}\n{}\n\nСвободных слотов: {}\nВыберите <b>время начала</b>:".format(
        data["resource_name"], date_label, free_count
    )
    await cb.message.edit_text(text, reply_markup=slots_keyboard(slots))
    await cb.answer()


# ---------- choose slot start ----------
@router.callback_query(BookingFlow.choose_slot_start, F.data.startswith("sstart_"))
async def on_slot_start(cb: CallbackQuery, state: FSMContext):
    # callback: sstart_HH-MM
    time_str = cb.data.replace("sstart_", "").replace("-", ":")
    data = await state.get_data()
    all_slots = data["slots_cache"]

    start_idx = next(
        (i for i, s in enumerate(all_slots) if s["start"] == time_str), None
    )
    if start_idx is None:
        await cb.answer("Слот не найден", show_alert=True)
        return

    # Считаем сколько подряд свободных слотов от start_idx
    max_consecutive = 0
    for i in range(start_idx, len(all_slots)):
        if not all_slots[i]["free"]:
            break
        max_consecutive += 1

    max_minutes = max_consecutive * settings.SLOT_MINUTES

    # Формируем доступные длительности
    available = [d for d in DURATION_OPTIONS if d <= max_minutes]
    if not available:
        await cb.answer("Минимум {} мин, но свободно меньше".format(DURATION_OPTIONS[0]), show_alert=True)
        return

    await state.update_data(slot_start=time_str)
    await state.set_state(BookingFlow.choose_slot_end)
    text = "{}\n{}\nНачало: <b>{}</b>\n\nВыберите <b>длительность</b>:".format(
        data["resource_name"], data["date_label"], time_str
    )
    await cb.message.edit_text(text, reply_markup=duration_keyboard(available))
    await cb.answer()


# ---------- choose duration ----------
@router.callback_query(BookingFlow.choose_slot_end, F.data.startswith("dur_"))
async def on_duration(cb: CallbackQuery, state: FSMContext):
    minutes = int(cb.data.replace("dur_", ""))
    data = await state.get_data()

    # Вычисляем время окончания
    sh, sm = map(int, data["slot_start"].split(":"))
    start_total = sh * 60 + sm
    end_total = start_total + minutes
    end_h = end_total // 60
    end_m = end_total % 60
    slot_end = "{:02d}:{:02d}".format(end_h, end_m)

    # Формируем читаемую длительность
    if minutes < 60:
        dur_label = "{} мин".format(minutes)
    elif minutes % 60 == 0:
        dur_label = "{} ч".format(minutes // 60)
    else:
        dur_label = "{}:{:02d}".format(minutes // 60, minutes % 60)

    await state.update_data(slot_end=slot_end, duration_label=dur_label)
    await state.set_state(BookingFlow.enter_name)
    text = "{}\n{}\n{} -- {} ({})\n\nВведите <b>ваше имя</b> (ФИО):".format(
        data["resource_name"], data["date_label"],
        data["slot_start"], slot_end, dur_label
    )
    await cb.message.edit_text(text)
    await cb.answer()


# ---------- enter name ----------
@router.message(BookingFlow.enter_name)
async def on_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Введите корректное имя (минимум 2 символа):")
        return

    await state.update_data(contact_name=name)
    await state.set_state(BookingFlow.enter_phone)
    await message.answer(
        "{}\n\nВведите <b>номер телефона</b> для связи:".format(name),
        reply_markup=skip_keyboard("phone"),
    )


# ---------- phone ----------
@router.callback_query(BookingFlow.enter_phone, F.data == "skip:phone")
async def skip_phone(cb: CallbackQuery, state: FSMContext):
    await state.update_data(contact_phone=None)
    await state.set_state(BookingFlow.enter_comment)
    await cb.message.edit_text(
        "Хотите оставить <b>комментарий</b>?\n(цель аренды, пожелания)",
        reply_markup=skip_keyboard("comment"),
    )
    await cb.answer()


@router.message(BookingFlow.enter_phone)
async def on_phone(message: Message, state: FSMContext):
    await state.update_data(contact_phone=message.text.strip())
    await state.set_state(BookingFlow.enter_comment)
    await message.answer(
        "Хотите оставить <b>комментарий</b>?\n(цель аренды, пожелания)",
        reply_markup=skip_keyboard("comment"),
    )


# ---------- comment ----------
@router.callback_query(BookingFlow.enter_comment, F.data == "skip:comment")
async def skip_comment(cb: CallbackQuery, state: FSMContext):
    await state.update_data(message=None)
    await _show_confirm(cb.message, state, edit=True)
    await cb.answer()


@router.message(BookingFlow.enter_comment)
async def on_comment(message: Message, state: FSMContext):
    await state.update_data(message=message.text.strip())
    await _show_confirm(message, state, edit=False)


# ---------- confirm ----------
async def _show_confirm(msg, state, edit):
    data = await state.get_data()
    await state.set_state(BookingFlow.confirm)

    org_name = data.get("org_name", "")
    resource = data["resource_name"]
    date_label = data["date_label"]
    slot_start = data["slot_start"]
    slot_end = data["slot_end"]
    dur_label = data.get("duration_label", "")
    name = data["contact_name"]
    phone = data.get("contact_phone") or "---"
    comment = data.get("message") or "---"

    text = (
        "<b>Проверьте заявку:</b>\n\n"
        "Учреждение: {}\n"
        "Площадка: {}\n"
        "Дата: {}\n"
        "Время: {} -- {} ({})\n\n"
        "Имя: {}\n"
        "Телефон: {}\n"
        "Комментарий: {}\n\n"
        "Всё верно?"
    ).format(org_name, resource, date_label, slot_start, slot_end, dur_label, name, phone, comment)

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
            "Ошибка сохранения. Попробуйте позже.\n/book"
        )
        await state.clear()
        await cb.answer()
        return

    ok_text = (
        "<b>Заявка #{} отправлена!</b>\n\n"
        "Площадка: {}\n"
        "Дата: {}\n"
        "Время: {} -- {}\n\n"
        "Сотрудник свяжется с вами.\n"
        "Статус заявки: /my"
    ).format(req_id, data["resource_name"], data["date_label"], data["slot_start"], data["slot_end"])

    await cb.message.edit_text(ok_text)
    await state.clear()
    await cb.answer()

    # Уведомляем сотрудников
    staff_ids = db.get_staff_chat_ids(data["org_id"])
    if staff_ids:
        username = cb.from_user.username or "---"
        phone = data.get("contact_phone") or "---"
        comment = data.get("message") or "---"
        org_name = data.get("org_name", "")

        staff_text = (
            "<b>Новая заявка #{}</b>\n\n"
            "Учреждение: {}\n"
            "Площадка: {}\n"
            "Дата: {}\n"
            "Время: {} -- {}\n\n"
            "Имя: {}\n"
            "Телефон: {}\n"
            "Комментарий: {}\n"
            "Telegram: @{}"
        ).format(
            req_id, org_name, data["resource_name"], data["date_label"],
            data["slot_start"], data["slot_end"], data["contact_name"],
            phone, comment, username
        )

        staff_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data="staff:confirm:{}".format(req_id),
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data="staff:reject:{}".format(req_id),
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
    await cb.message.edit_text("Отменено.\n\n/book -- начать заново")
    await cb.answer()


# ---------- restart ----------
@router.callback_query(F.data == "restart")
async def on_restart(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    orgs = db.load_orgs()
    if len(orgs) == 1:
        org = orgs[0]
        await state.update_data(org_id=org["id"], org_name=org["name"])
        resources = db.load_resources(org["id"])
        await state.set_state(BookingFlow.choose_resource)
        text = "<b>{}</b>\n\nВыберите площадку:".format(org["name"])
        await cb.message.edit_text(text, reply_markup=resource_keyboard(resources))
    elif orgs:
        await state.set_state(BookingFlow.choose_org)
        await cb.message.edit_text(
            "Выберите учреждение:", reply_markup=org_keyboard(orgs)
        )
    else:
        await cb.message.edit_text("Нет учреждений.")
    await cb.answer()


# ---------- back buttons ----------
@router.callback_query(F.data == "back:org")
async def back_org(cb: CallbackQuery, state: FSMContext):
    orgs = db.load_orgs()
    await state.set_state(BookingFlow.choose_org)
    await cb.message.edit_text(
        "Выберите учреждение:", reply_markup=org_keyboard(orgs)
    )
    await cb.answer()


@router.callback_query(F.data == "back:resource")
async def back_resource(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    resources = db.load_resources(data["org_id"])
    await state.set_state(BookingFlow.choose_resource)
    text = "<b>{}</b>\n\nВыберите площадку:".format(data.get("org_name", ""))
    await cb.message.edit_text(text, reply_markup=resource_keyboard(resources))
    await cb.answer()


@router.callback_query(F.data == "back:date")
async def back_date(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BookingFlow.choose_date)
    text = "<b>{}</b>\n\nВыберите дату:".format(data["resource_name"])
    await cb.message.edit_text(text, reply_markup=date_keyboard())
    await cb.answer()


@router.callback_query(F.data == "back:slot_start")
async def back_slot_start(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    slots = data.get("slots_cache", [])
    await state.set_state(BookingFlow.choose_slot_start)
    text = "{}\n{}\n\nВыберите <b>время начала</b>:".format(
        data["resource_name"], data["date_label"]
    )
    await cb.message.edit_text(text, reply_markup=slots_keyboard(slots))
    await cb.answer()
