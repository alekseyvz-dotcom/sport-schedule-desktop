from __future__ import annotations

import logging
from datetime import date, timedelta, time, datetime

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

# Варианты длительности бронирования (минуты)
DURATION_OPTIONS = [60, 90, 120]

ORG_BRAND = "Московская футбольная академия"


# ───────────────────────── UI helpers ─────────────────────────

def _fmt_hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def _org_hours(org: dict) -> str:
    if org.get("is_24h"):
        return "круглосуточно"
    ws = org.get("work_start")
    we = org.get("work_end")
    if ws and we:
        return f"{_fmt_hhmm(ws)}–{_fmt_hhmm(we)}"
    return "—"


def org_card(org: dict, with_title: bool = True) -> str:
    name = org.get("name") or "—"
    addr = org.get("address") or "—"
    hours = _org_hours(org)
    if with_title:
        return (
            f"⚽ <b>{ORG_BRAND}</b>\n"
            f"🏢 <b>{name}</b>\n"
            f"📍 <i>{addr}</i>\n"
            f"🕒 Часы работы: <b>{hours}</b>"
        )
    return (
        f"🏢 <b>{name}</b>\n"
        f"📍 <i>{addr}</i>\n"
        f"🕒 Часы работы: <b>{hours}</b>"
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Создать заявку", callback_data="menu:book")],
        [InlineKeyboardButton(text="📋 Мои заявки", callback_data="menu:my")],
        [InlineKeyboardButton(text="ℹ️ Как это работает", callback_data="menu:help")],
    ])


def org_keyboard(orgs):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=o["name"], callback_data=f"org:{o['id']}")]
        for o in orgs
    ])


def resource_keyboard(resources):
    buttons = [
        [InlineKeyboardButton(text=r["name"], callback_data=f"res:{r['venue_id']}")]
        for r in resources
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:org")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def portion_keyboard(portion_options: list[dict]):
    """Клавиатура выбора части площадки (1/4, 1/2, целая)."""
    buttons = [
        [InlineKeyboardButton(text=opt["label"], callback_data=opt["callback"])]
        for opt in portion_options
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:resource")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def date_keyboard():
    today = date.today()
    buttons = []
    row = []
    for i in range(settings.MAX_DAYS_AHEAD):
        d = today + timedelta(days=i)
        if i == 0:
            label = "Сегодня"
        elif i == 1:
            label = "Завтра"
        else:
            label = f"{d.strftime('%d.%m')} ({WEEKDAYS[d.weekday()]})"

        row.append(InlineKeyboardButton(text=label, callback_data=f"date_{d.isoformat()}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:portion")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def slots_keyboard(slots_cache):
    """Выбор времени начала."""
    free_slots = [s for s in slots_cache if s["free"]]
    if not free_slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Другая дата", callback_data="back:date")]
        ])

    buttons = []
    row = []
    for s in free_slots:
        label = _time_display(s["start"])
        row.append(InlineKeyboardButton(text=label, callback_data=f"slot_{s['start']}"))
        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:date")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def duration_keyboard(slot_start_str, slots_cache, org_work_end):
    """Выбор длительности."""
    sh, sm = map(int, slot_start_str.split("-"))
    start_minutes = sh * 60 + sm

    if org_work_end:
        work_end_minutes = org_work_end.hour * 60 + org_work_end.minute
    else:
        work_end_minutes = 24 * 60

    start_idx = next(
        (i for i, s in enumerate(slots_cache) if s["start"] == slot_start_str),
        None,
    )

    max_free_minutes = 0
    if start_idx is not None:
        for i in range(start_idx, len(slots_cache)):
            if not slots_cache[i]["free"]:
                break
            max_free_minutes += settings.SLOT_MINUTES

        max_slots = min(settings.MAX_BOOKING_SLOTS, len(slots_cache) - start_idx)
        max_free_minutes = min(max_free_minutes, max_slots * settings.SLOT_MINUTES)

    if work_end_minutes > start_minutes:
        max_free_minutes = min(max_free_minutes, work_end_minutes - start_minutes)

    allowed = []
    for dur in DURATION_OPTIONS:
        if dur <= max_free_minutes and dur % settings.SLOT_MINUTES == 0:
            allowed.append(dur)

    buttons = []
    row = []
    for dur in allowed:
        end_total = start_minutes + dur
        end_h = end_total // 60
        end_m = end_total % 60
        if end_h >= 24:
            continue

        end_str = f"{end_h:02d}-{end_m:02d}"
        row.append(InlineKeyboardButton(
            text=_format_duration(dur),
            callback_data=f"dur_{end_str}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    if not buttons:
        buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="back:slot_start")]]
    else:
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:slot_start")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_duration(minutes):
    if minutes < 60:
        return f"{minutes} мин"
    h = minutes // 60
    m = minutes % 60
    if m == 0:
        return f"{h} ч"
    return f"{h} ч {m} мин"


def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="confirm:yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:no"),
        ],
        [InlineKeyboardButton(text="🔄 Начать заново", callback_data="restart")],
    ])


def after_success_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новая заявка", callback_data="restart")],
        [InlineKeyboardButton(text="📋 Мои заявки", callback_data="menu:my")],
    ])


def skip_keyboard(field):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить ▶️", callback_data=f"skip:{field}")]
    ])


# ─── Time encoding helpers (callback_data safe: HH-MM) ───

def _time_display(hhmm_str):
    return hhmm_str.replace("-", ":")


def _parse_time(hhmm_str):
    h, m = map(int, hhmm_str.split("-"))
    return time(h, m)


# ─── Portion label helper ───

def _portion_label(units_needed: int, total_units: int) -> str:
    """Человекочитаемый лейбл для части площадки."""
    if total_units == 0 or units_needed >= total_units:
        return "Целое поле"
    fraction = units_needed / total_units
    if abs(fraction - 0.25) < 0.01:
        return "1/4 поля"
    elif abs(fraction - 0.5) < 0.01:
        return "1/2 поля"
    elif abs(fraction - 0.75) < 0.01:
        return "3/4 поля"
    else:
        return f"{units_needed}/{total_units} поля"


# ───────────────────────── Commands / Menu ─────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        f"⚽ <b>{ORG_BRAND}</b>\n"
        f"<b>Бронирование залов и площадок</b>\n\n"
        "Выберите действие:"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "ℹ️ <b>Как работает бронирование</b>\n\n"
        "1) Выберите учреждение и площадку\n"
        "2) Укажите какую часть площадки хотите забронировать\n"
        "3) Выберите дату и время начала\n"
        "4) Укажите длительность\n"
        "5) Оставьте контакты\n"
        "6) Подтвердите отправку заявки\n\n"
        "После отправки заявка поступает администратору.\n"
        "Статусы и история: /my"
    )
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext):
    await _start_booking(message, state)


@router.message(Command("my"))
async def cmd_my(message: Message):
    await _send_my_requests(message.from_user.id, message)


@router.callback_query(F.data == "menu:book")
async def menu_book(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await _start_booking(cb.message, state, edit=True)


@router.callback_query(F.data == "menu:help")
async def menu_help(cb: CallbackQuery):
    await cb.answer()
    text = (
        "ℹ️ <b>Как работает бронирование</b>\n\n"
        "1) Выберите учреждение и площадку\n"
        "2) Укажите какую часть площадки хотите забронировать\n"
        "3) Выберите дату и время начала\n"
        "4) Укажите длительность\n"
        "5) Оставьте контакты\n"
        "6) Подтвердите отправку заявки\n\n"
        "После отправки заявка поступает администратору.\n"
        "Статусы и история: /my"
    )
    await cb.message.edit_text(text)


@router.callback_query(F.data == "menu:my")
async def menu_my(cb: CallbackQuery):
    await cb.answer()
    await _send_my_requests(cb.from_user.id, cb.message, edit=True)


async def _send_my_requests(telegram_user_id: int, msg: Message, edit: bool = False):
    rows = db.get_user_requests(telegram_user_id)
    if not rows:
        text = "📋 <b>Мои заявки</b>\n\nПока заявок нет.\nНажмите /book или кнопку «Создать заявку»."
        if edit:
            await msg.edit_text(text)
        else:
            await msg.answer(text)
        return

    status_emoji = {
        "new": "🆕",
        "confirmed": "✅",
        "rejected": "❌",
        "cancelled": "🚫",
    }

    lines = ["📋 <b>Мои последние заявки</b>\n"]
    for r in rows:
        emoji = status_emoji.get(r["status"], "❓")
        date_str = r["desired_date"].strftime("%d.%m.%Y")
        start_str = r["desired_start"].strftime("%H:%M")
        end_str = r["desired_end"].strftime("%H:%M")
        venue = r["venue_name"]
        unit = f" ({r['unit_name']})" if r.get("unit_name") else ""
        comment = f"\n   💬 {r['staff_comment']}" if r.get("staff_comment") else ""
        lines.append(
            f"{emoji} <b>#{r['id']}</b>  {date_str} {start_str}–{end_str}\n"
            f"   📍 {venue}{unit}{comment}"
        )

    text = "\n".join(lines)
    if edit:
        await msg.edit_text(text)
    else:
        await msg.answer(text)


async def _start_booking(msg: Message, state: FSMContext, edit: bool = False):
    await state.clear()
    orgs = db.load_orgs()
    if not orgs:
        text = "😔 Сейчас нет доступных учреждений."
        if edit:
            await msg.edit_text(text)
        else:
            await msg.answer(text)
        return

    if len(orgs) == 1:
        org = db.get_org(orgs[0]["id"]) or orgs[0]
        await state.update_data(org_id=org["id"], org_name=org["name"])
        resources = db.load_resources(org["id"])
        if not resources:
            text = org_card(org) + "\n\n😔 Нет доступных площадок."
            if edit:
                await msg.edit_text(text)
            else:
                await msg.answer(text)
            return

        await state.set_state(BookingFlow.choose_resource)
        text = org_card(org) + "\n\n<b>Шаг 1.</b> Выберите площадку:"
        if edit:
            await msg.edit_text(text, reply_markup=resource_keyboard(resources))
        else:
            await msg.answer(text, reply_markup=resource_keyboard(resources))
        return

    await state.set_state(BookingFlow.choose_org)
    text = (
        f"⚽ <b>{ORG_BRAND}</b>\n"
        "<b>Шаг 1.</b> Выберите учреждение:"
    )
    if edit:
        await msg.edit_text(text, reply_markup=org_keyboard(orgs))
    else:
        await msg.answer(text, reply_markup=org_keyboard(orgs))


# ───────────────────────── Booking flow ─────────────────────────

@router.callback_query(BookingFlow.choose_org, F.data.startswith("org:"))
async def on_org(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    org_id = int(cb.data.split(":")[1])
    org = db.get_org(org_id)
    if not org:
        await cb.answer("Не найдено", show_alert=True)
        return

    await state.update_data(org_id=org_id, org_name=org["name"])
    resources = db.load_resources(org_id)
    if not resources:
        await cb.message.edit_text(org_card(org) + "\n\n😔 Нет доступных площадок.")
        return

    await state.set_state(BookingFlow.choose_resource)
    text = org_card(org) + "\n\n<b>Шаг 2.</b> Выберите площадку:"
    await cb.message.edit_text(text, reply_markup=resource_keyboard(resources))


@router.callback_query(BookingFlow.choose_resource, F.data.startswith("res:"))
async def on_resource(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    venue_id = int(cb.data.split(":")[1])

    data = await state.get_data()
    resources = db.load_resources(data["org_id"])
    resource = next((r for r in resources if r["venue_id"] == venue_id), None)
    if not resource:
        await cb.answer("Площадка не найдена", show_alert=True)
        return

    await state.update_data(
        venue_id=venue_id,
        resource_name=resource["name"],
    )

    # Проверяем варианты разбиения
    portion_options = db.get_portion_options(venue_id)

    if not portion_options:
        # Площадка не делится — пропускаем шаг
        units = db.load_venue_units(venue_id)
        total_units = len(units)
        await state.update_data(
            units_needed=0,
            total_units=total_units,
            portion_label="",
        )
        await state.set_state(BookingFlow.choose_date)
        text = (
            f"📍 <b>{resource['name']}</b>\n\n"
            "<b>Выберите дату:</b>"
        )
        await cb.message.edit_text(text, reply_markup=date_keyboard())
    else:
        # Показываем выбор части + прайс-лист
        total_units = len(db.load_venue_units(venue_id))
        price_text = db.format_price_list(venue_id, total_units)

        await state.update_data(
            total_units=total_units,
            portion_options=[
                {"label": o["label"], "units_needed": o["units_needed"], "callback": o["callback"]}
                for o in portion_options
            ],
        )
        await state.set_state(BookingFlow.choose_portion)

        price_block = f"\n\n{price_text}" if price_text else ""

        text = (
            f"📍 <b>{resource['name']}</b>\n\n"
            f"🏟 <b>Какую часть площадки вы хотите забронировать?</b>"
            f"{price_block}"
        )
        await cb.message.edit_text(text, reply_markup=portion_keyboard(portion_options))

# ─── НОВЫЙ ШАГ: выбор части площадки ───

@router.callback_query(BookingFlow.choose_portion, F.data.startswith("portion:"))
async def on_portion(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()

    # Парсим callback: "portion:N" или "portion:1:unit:ID"
    parts = cb.data.split(":")
    units_needed = int(parts[1])

    # Определяем лейбл
    total_units = data.get("total_units", 0)
    portion_label = _portion_label(units_needed, total_units)

    await state.update_data(
        units_needed=units_needed,
        portion_label=portion_label,
    )
    await state.set_state(BookingFlow.choose_date)

    text = (
        f"📍 <b>{data['resource_name']}</b>\n"
        f"🏟 <b>{portion_label}</b>\n\n"
        "<b>Выберите дату:</b>"
    )
    await cb.message.edit_text(text, reply_markup=date_keyboard())


@router.callback_query(BookingFlow.choose_date, F.data.startswith("date_"))
async def on_date(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    d = date.fromisoformat(cb.data[5:])
    data = await state.get_data()

    if not db.is_venue_available(data["venue_id"], data["org_id"], d):
        await cb.answer("❌ Площадка закрыта в этот день", show_alert=True)
        return

    units_needed = data.get("units_needed", 0)

    slots = db.compute_free_slots(
        data["venue_id"], None, data["org_id"], d,
        units_needed=units_needed,
    )
    free_count = sum(1 for s in slots if s["free"])
    if free_count == 0:
        await cb.answer("😔 Нет свободного времени", show_alert=True)
        return

    date_label = f"{d.strftime('%d.%m.%Y')} ({WEEKDAYS[d.weekday()]})"

    slots_cache = []
    for s in slots:
        start_str = (
            s["start"].strftime("%H-%M")
            if hasattr(s["start"], "strftime")
            else str(s["start"]).replace(":", "-")
        )
        end_str = (
            s["end"].strftime("%H-%M")
            if hasattr(s["end"], "strftime")
            else str(s["end"]).replace(":", "-")
        )
        slots_cache.append({"start": start_str, "end": end_str, "free": s["free"]})

    await state.update_data(
        desired_date=d.isoformat(),
        date_label=date_label,
        slots_cache=slots_cache,
    )
    await state.set_state(BookingFlow.choose_slot_start)

    portion_label = data.get("portion_label", "")
    portion_line = f"🏟 <b>{portion_label}</b>\n" if portion_label else ""

    text = (
        f"📍 <b>{data['resource_name']}</b>\n"
        f"{portion_line}"
        f"📅 <b>{date_label}</b>\n\n"
        f"Свободных интервалов: <b>{free_count}</b>\n"
        "<b>Выберите время начала:</b>"
    )
    await cb.message.edit_text(text, reply_markup=slots_keyboard(slots_cache))


@router.callback_query(BookingFlow.choose_slot_start, F.data.startswith("slot_"))
async def on_slot_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    start_str = cb.data[5:]  # HH-MM
    data = await state.get_data()

    org = db.get_org(data["org_id"])
    org_work_end = None
    if org and not org.get("is_24h"):
        org_work_end = org.get("work_end")

    await state.update_data(slot_start=start_str)
    await state.set_state(BookingFlow.choose_slot_end)

    portion_label = data.get("portion_label", "")
    portion_line = f"🏟 <b>{portion_label}</b>\n" if portion_label else ""

    text = (
        f"📍 <b>{data['resource_name']}</b>\n"
        f"{portion_line}"
        f"📅 <b>{data['date_label']}</b>\n"
        f"🕐 Начало: <b>{_time_display(start_str)}</b>\n\n"
        "Выберите длительность:"
    )
    await cb.message.edit_text(
        text,
        reply_markup=duration_keyboard(start_str, data["slots_cache"], org_work_end),
    )


@router.callback_query(BookingFlow.choose_slot_end, F.data.startswith("dur_"))
async def on_duration(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    end_str = cb.data[4:]  # HH-MM
    data = await state.get_data()

    # Вычисляем длительность в минутах
    sh, sm = map(int, data['slot_start'].split("-"))
    eh, em = map(int, end_str.split("-"))
    duration_minutes = (eh * 60 + em) - (sh * 60 + sm)

    # Вычисляем цену
    units_needed = data.get("units_needed", 0)
    total_units = data.get("total_units", 0)
    price = db.compute_booking_price(
        data["venue_id"], units_needed, total_units, duration_minutes
    )

    price_str = str(price) if price is not None else None
    await state.update_data(slot_end=end_str, booking_price=price_str)
    await state.set_state(BookingFlow.enter_name)

    portion_label = data.get("portion_label", "")
    portion_line = f"🏟 <b>{portion_label}</b>\n" if portion_label else ""

    price_line = ""
    if price is not None:
        price_line = f"\n💰 Расчётная стоимость составит от <b>{int(price)} ₽</b>"

    text = (
        f"📍 <b>{data['resource_name']}</b>\n"
        f"{portion_line}"
        f"📅 <b>{data['date_label']}</b>\n"
        f"🕐 <b>{_time_display(data['slot_start'])} – {_time_display(end_str)}</b>"
        f"{price_line}\n\n"
        "Введите <b>ваше имя</b> (ФИО):"
    )
    await cb.message.edit_text(text)


@router.message(BookingFlow.enter_name)
async def on_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введите корректное имя (минимум 2 символа):")
        return

    await state.update_data(contact_name=name)
    await state.set_state(BookingFlow.enter_phone)
    await message.answer(
        "📞 Введите <b>номер телефона</b> для связи:",
        reply_markup=skip_keyboard("phone"),
    )


@router.callback_query(BookingFlow.enter_phone, F.data == "skip:phone")
async def skip_phone(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(contact_phone=None)
    await state.set_state(BookingFlow.enter_comment)
    await cb.message.edit_text(
        "💬 Хотите оставить <b>комментарий</b>?\n<i>(цель аренды, пожелания)</i>",
        reply_markup=skip_keyboard("comment"),
    )


@router.message(BookingFlow.enter_phone)
async def on_phone(message: Message, state: FSMContext):
    await state.update_data(contact_phone=(message.text or "").strip())
    await state.set_state(BookingFlow.enter_comment)
    await message.answer(
        "💬 Хотите оставить <b>комментарий</b>?\n<i>(цель аренды, пожелания)</i>",
        reply_markup=skip_keyboard("comment"),
    )


@router.callback_query(BookingFlow.enter_comment, F.data == "skip:comment")
async def skip_comment(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(message=None)
    await _show_confirm(cb.message, state, edit=True)


@router.message(BookingFlow.enter_comment)
async def on_comment(message: Message, state: FSMContext):
    await state.update_data(message=(message.text or "").strip())
    await _show_confirm(message, state, edit=False)


async def _show_confirm(msg: Message, state: FSMContext, edit: bool):
    data = await state.get_data()
    await state.set_state(BookingFlow.confirm)

    org_name = data.get("org_name", "—")
    resource = data.get("resource_name", "—")
    portion_label = data.get("portion_label", "")
    date_label = data.get("date_label", "—")
    slot_start = _time_display(data["slot_start"])
    slot_end = _time_display(data["slot_end"])
    name = data.get("contact_name", "—")
    phone = data.get("contact_phone") or "—"
    comment = data.get("message") or "—"
    booking_price = data.get("booking_price")

    portion_line = f"🏟 {portion_label}\n" if portion_label else ""

    price_line = ""
    if booking_price:
        price_line = f"💰 Расчётная стоимость составит от <b>{int(float(booking_price))} ₽</b>\n"

    text = (
        "✅ <b>Проверка заявки</b>\n\n"
        "<b>Детали бронирования</b>\n"
        f"🏢 {org_name}\n"
        f"📍 {resource}\n"
        f"{portion_line}"
        f"📅 {date_label}\n"
        f"🕐 {slot_start} – {slot_end}\n"
        f"{price_line}\n"
        "<b>Контакты</b>\n"
        f"👤 {name}\n"
        f"📞 {phone}\n"
        f"💬 {comment}\n\n"
        "Отправить заявку администратору?"
    )

    if edit:
        await msg.edit_text(text, reply_markup=confirm_keyboard())
    else:
        await msg.answer(text, reply_markup=confirm_keyboard())


@router.callback_query(BookingFlow.confirm, F.data == "confirm:yes")
async def on_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    data = await state.get_data()

    d = date.fromisoformat(data["desired_date"])
    start_time = _parse_time(data["slot_start"])
    end_time = _parse_time(data["slot_end"])

    # Определяем конкретные свободные unit_id
    units_needed = data.get("units_needed", 0)
    venue_unit_ids = None

    if units_needed > 0:
        free_ids = db.find_free_unit_ids(
            data["venue_id"], data["org_id"], d,
            start_time, end_time, units_needed,
        )
        if not free_ids:
            await cb.message.edit_text(
                "😔 К сожалению, выбранное время уже занято.\n"
                "Попробуйте выбрать другое время.\n\n/book"
            )
            await state.clear()
            return
        venue_unit_ids = free_ids

    req_data = {
        "org_id":           data["org_id"],
        "venue_id":         data["venue_id"],
        "venue_unit_id":    None,
        "venue_unit_ids":   venue_unit_ids,
        "desired_date":     d,
        "desired_start":    start_time,
        "desired_end":      end_time,
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
        await cb.message.edit_text("❌ Не удалось сохранить заявку. Попробуйте позже.\n\n/book")
        await state.clear()
        return

    portion_label = data.get("portion_label", "")
    portion_line = f"🏟 <b>{portion_label}</b>\n" if portion_label else ""
    booking_price = data.get("booking_price")
    price_line = ""
    if booking_price:
        price_line = f"💰 Расчётная стоимость составит от <b>{int(float(booking_price))} ₽</b>\n"

    ok_text = (
        f"✅ <b>Заявка #{req_id} отправлена!</b>\n\n"
        f"📍 <b>{data['resource_name']}</b>\n"
        f"{portion_line}"
        f"📅 <b>{data['date_label']}</b>\n"
        f"🕐 <b>{_time_display(data['slot_start'])} – {_time_display(data['slot_end'])}</b>\n"
        f"{price_line}\n"
        "Администратор получит уведомление и свяжется с вами.\n"
        "Статус заявки: /my"
    )

    await cb.message.edit_text(ok_text, reply_markup=after_success_keyboard())
    await state.clear()

    # Notify staff
    staff_ids = db.get_staff_chat_ids(data["org_id"])
    if staff_ids:
        username = cb.from_user.username or "—"
        phone = data.get("contact_phone") or "—"
        comment = data.get("message") or "—"
        org_name = data.get("org_name", "")

        staff_price_line = ""
        if booking_price:
            staff_price_line = f"💰 Расч. стоимость: от {int(float(booking_price))} ₽\n"

        staff_text = (
            f"📩 <b>Новая заявка #{req_id}</b>\n\n"
            f"🏢 {org_name}\n"
            f"📍 {data['resource_name']}\n"
            f"{portion_line}"
            f"📅 {data['date_label']}\n"
            f"🕐 {_time_display(data['slot_start'])} – {_time_display(data['slot_end'])}\n"
            f"{staff_price_line}\n"
            f"👤 {data['contact_name']}\n"
            f"📞 {phone}\n"
            f"💬 {comment}\n"
            f"🆔 @{username}"
        )

        staff_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"staff:confirm:{req_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"staff:reject:{req_id}"),
            ],
        ])

        for chat_id in staff_ids:
            try:
                await bot.send_message(chat_id, staff_text, reply_markup=staff_kb)
            except Exception:
                log.exception("Failed to notify staff %s", chat_id)

@router.callback_query(BookingFlow.confirm, F.data == "confirm:no")
async def on_cancel(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.edit_text(
        "🚫 Заявка отменена.\n\n"
        "Хотите создать новую?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать заявку", callback_data="menu:book")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="restart")],
        ]),
    )


# ───────────────────────── Navigation ─────────────────────────

@router.callback_query(F.data == "restart")
async def on_restart(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    text = (
        f"⚽ <b>{ORG_BRAND}</b>\n"
        "<b>Бронирование залов и площадок</b>\n\n"
        "Выберите действие:"
    )
    await cb.message.edit_text(text, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "back:org")
async def back_org(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    orgs = db.load_orgs()
    await state.set_state(BookingFlow.choose_org)
    await cb.message.edit_text(
        f"⚽ <b>{ORG_BRAND}</b>\n<b>Шаг 1.</b> Выберите учреждение:",
        reply_markup=org_keyboard(orgs),
    )


@router.callback_query(F.data == "back:resource")
async def back_resource(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    org = db.get_org(data["org_id"]) if data.get("org_id") else None

    resources = db.load_resources(data["org_id"])
    await state.set_state(BookingFlow.choose_resource)
    header = org_card(org, with_title=True) if org else f"⚽ <b>{ORG_BRAND}</b>"
    await cb.message.edit_text(
        header + "\n\n<b>Выберите площадку:</b>",
        reply_markup=resource_keyboard(resources),
    )


@router.callback_query(F.data == "back:portion")
async def back_portion(cb: CallbackQuery, state: FSMContext):
    """Назад к выбору части площадки (или к площадкам если деления нет)."""
    await cb.answer()
    data = await state.get_data()

    portion_options = data.get("portion_options")
    if portion_options:
        # Площадка делится — показываем выбор части
        await state.set_state(BookingFlow.choose_portion)
        text = (
            f"📍 <b>{data.get('resource_name', '—')}</b>\n\n"
            "🏟 <b>Какую часть площадки вы хотите забронировать?</b>"
        )
        await cb.message.edit_text(text, reply_markup=portion_keyboard(portion_options))
    else:
        # Площадка не делится — возвращаемся к списку площадок
        org = db.get_org(data["org_id"]) if data.get("org_id") else None
        resources = db.load_resources(data["org_id"])
        await state.set_state(BookingFlow.choose_resource)
        header = org_card(org, with_title=True) if org else f"⚽ <b>{ORG_BRAND}</b>"
        await cb.message.edit_text(
            header + "\n\n<b>Выберите площадку:</b>",
            reply_markup=resource_keyboard(resources),
        )


@router.callback_query(F.data == "back:date")
async def back_date(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    await state.set_state(BookingFlow.choose_date)

    portion_label = data.get("portion_label", "")
    portion_line = f"🏟 <b>{portion_label}</b>\n" if portion_label else ""

    await cb.message.edit_text(
        f"📍 <b>{data.get('resource_name', '—')}</b>\n"
        f"{portion_line}\n"
        "<b>Выберите дату:</b>",
        reply_markup=date_keyboard(),
    )

@router.callback_query(F.data == "back:slot_start")
async def back_slot_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    slots_cache = data.get("slots_cache", [])
    await state.set_state(BookingFlow.choose_slot_start)

    portion_label = data.get("portion_label", "")
    portion_line = f"🏟 <b>{portion_label}</b>\n" if portion_label else ""

    await cb.message.edit_text(
        f"📍 <b>{data.get('resource_name', '—')}</b>\n"
        f"{portion_line}"
        f"📅 <b>{data.get('date_label', '—')}</b>\n\n"
        "<b>Выберите время начала:</b>",
        reply_markup=slots_keyboard(slots_cache),
    )
