# app/ui/schedule_windows_view.py
"""
Свободные окна по объекту (ТЗ, п. 8).

Свободное время считается автоматически: из окна работы учреждения вычитаются
все занятия объекта. Результат раскладывается по периодам
утро / день / вечер и показывается на день, неделю или месяц.

Модуль только читает данные.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.services import bookings_service, ref_service
from app.services.day_parts_settings_service import get_day_parts_settings
from app.services.users_service import AuthUser
from app.services.venue_units_service import list_venue_units

APP_TZ = timezone(timedelta(hours=3))

WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_NOM = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)

MIN_SLOT_MINUTES = 15          # окна короче 15 минут не показываем
PART_ORDER = ("morning", "day", "evening")


# ──────────────────────────────────────────────────────────────────────────────
# расчёт интервалов (чистые функции — их удобно проверять тестами)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))


def merge_intervals(items: Sequence[Interval]) -> List[Interval]:
    """Склеивает пересекающиеся и соприкасающиеся интервалы."""
    if not items:
        return []

    ordered = sorted(items, key=lambda i: (i.start, i.end))
    out: List[Interval] = [ordered[0]]

    for cur in ordered[1:]:
        last = out[-1]
        if cur.start <= last.end:
            if cur.end > last.end:
                out[-1] = Interval(last.start, cur.end)
        else:
            out.append(cur)
    return out


def subtract_intervals(base: Interval, busy: Sequence[Interval]) -> List[Interval]:
    """Возвращает свободные куски base за вычетом busy."""
    if base.end <= base.start:
        return []

    clipped = [
        Interval(max(b.start, base.start), min(b.end, base.end))
        for b in busy
        if b.end > base.start and b.start < base.end
    ]
    merged = merge_intervals([c for c in clipped if c.end > c.start])

    out: List[Interval] = []
    cursor = base.start
    for m in merged:
        if m.start > cursor:
            out.append(Interval(cursor, m.start))
        if m.end > cursor:
            cursor = m.end
    if cursor < base.end:
        out.append(Interval(cursor, base.end))

    return [i for i in out if i.minutes >= MIN_SLOT_MINUTES]


def split_by_parts(
    free: Sequence[Interval],
    parts: Sequence[Tuple[str, time, time]],
) -> Dict[str, List[Interval]]:
    """Раскладывает свободные интервалы по периодам утро/день/вечер."""
    out: Dict[str, List[Interval]] = {key: [] for key, _s, _e in parts}

    for key, p_start, p_end in parts:
        day = free[0].start.date() if free else None
        if day is None:
            continue
        p_from = datetime.combine(day, p_start, tzinfo=APP_TZ)
        p_to = datetime.combine(day, p_end, tzinfo=APP_TZ)
        for iv in free:
            s = max(iv.start, p_from)
            e = min(iv.end, p_to)
            if e > s and int((e - s).total_seconds() // 60) >= MIN_SLOT_MINUTES:
                out[key].append(Interval(s, e))
    return out


def parse_part(value: str) -> time:
    hh, mm = value.split(":")
    return time(hour=int(hh), minute=int(mm))


def build_day_parts(settings) -> List[Tuple[str, time, time]]:
    """
    Периоды из настроек учреждения.
    Если настройки пустые или некорректные — берём значения из ТЗ:
    утро 08:00–12:00, день 12:00–18:00, вечер 18:00–23:00.
    """
    try:
        m_s, m_e = settings.morning_interval()
        d_s, d_e = settings.day_interval()
        e_s, e_e = settings.evening_interval()
        parts = [
            ("morning", m_s, m_e),
            ("day", d_s, d_e),
            ("evening", e_s, e_e),
        ]
        if all(s < e for _k, s, e in parts):
            return parts
    except Exception:
        pass

    return [
        ("morning", time(8, 0), time(12, 0)),
        ("day", time(12, 0), time(18, 0)),
        ("evening", time(18, 0), time(23, 0)),
    ]


def format_hhmm(dt: datetime) -> str:
    return dt.astimezone(APP_TZ).strftime("%H:%M")


def format_duration(minutes: int) -> str:
    if minutes <= 0:
        return "—"
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours} ч {mins} мин"
    if hours:
        return f"{hours} ч"
    return f"{mins} мин"


def format_intervals(items: Sequence[Interval]) -> str:
    if not items:
        return ""
    return ", ".join(f"{format_hhmm(i.start)}–{format_hhmm(i.end)}" for i in items)


def free_intervals_for_day(
    day: date,
    work_start: time,
    work_end: time,
    bookings: Sequence,
    *,
    venue_unit_id: Optional[int] = None,
) -> List[Interval]:
    """Свободные интервалы одного дня по объекту (или по конкретной площадке)."""
    base = Interval(
        datetime.combine(day, work_start, tzinfo=APP_TZ),
        datetime.combine(day, work_end, tzinfo=APP_TZ),
    )

    busy: List[Interval] = []
    for b in bookings:
        if (getattr(b, "status", "") or "").lower() == "cancelled":
            continue
        if venue_unit_id is not None:
            unit = getattr(b, "venue_unit_id", None)
            if unit is not None and int(unit) != int(venue_unit_id):
                continue
        busy.append(Interval(b.starts_at, b.ends_at))

    return subtract_intervals(base, busy)


def period_days(anchor: date, mode: str) -> List[date]:
    if mode == "day":
        return [anchor]
    if mode == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return [start + timedelta(days=i) for i in range(7)]

    first = anchor.replace(day=1)
    next_month = (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    )
    last = next_month - timedelta(days=1)

    out: List[date] = []
    cur = first
    while cur <= last:
        out.append(cur)
        cur += timedelta(days=1)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# экран
# ──────────────────────────────────────────────────────────────────────────────

class ScheduleWindowsView(QWidget):
    """
    Публичный API:
        view.set_org(org_id, work_start, work_end)
        view.reload()

    Сигнал requestOpenDay(date) — переход в расписание на выбранный день.
    """

    requestOpenDay = Signal(object)

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("windowsView")
        self.user = user

        self._org_id: Optional[int] = None
        self._work_start = time(8, 0)
        self._work_end = time(22, 0)

        self._anchor: date = date.today()
        self._venues: List = []
        self._units: List = []
        self._parts: List[Tuple[str, time, time]] = build_day_parts(None)

        # ── панель управления ──────────────────────────────────────────────
        self.cmb_venue = QComboBox()
        self.cmb_venue.setMinimumWidth(230)
        self.cmb_venue.currentIndexChanged.connect(self._on_venue_changed)

        self.cmb_unit = QComboBox()
        self.cmb_unit.setMinimumWidth(160)
        self.cmb_unit.currentIndexChanged.connect(lambda *_: self.reload())

        self.cmb_period = QComboBox()
        self.cmb_period.addItem("День", "day")
        self.cmb_period.addItem("Неделя", "week")
        self.cmb_period.addItem("Месяц", "month")
        self.cmb_period.currentIndexChanged.connect(lambda *_: self.reload())

        self.btn_prev = QToolButton()
        self.btn_prev.setText("◀")
        self.btn_prev.setObjectName("monthNav")
        self.btn_prev.clicked.connect(lambda: self._shift(-1))

        self.btn_next = QToolButton()
        self.btn_next.setText("▶")
        self.btn_next.setObjectName("monthNav")
        self.btn_next.clicked.connect(lambda: self._shift(1))

        self.lbl_month = QLabel("")
        self.lbl_month.setObjectName("monthTitle")
        self.lbl_month.setMinimumWidth(180)
        self.lbl_month.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_today = QPushButton("Сегодня")
        self.btn_today.clicked.connect(self._go_today)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.clicked.connect(self.reload)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("scheduleMeta")

        top = QHBoxLayout()
        top.setContentsMargins(12, 10, 12, 6)
        top.setSpacing(8)
        top.addWidget(QLabel("Объект:"))
        top.addWidget(self.cmb_venue, 1)
        top.addWidget(QLabel("Площадка:"))
        top.addWidget(self.cmb_unit)
        top.addSpacing(10)
        top.addWidget(QLabel("Период:"))
        top.addWidget(self.cmb_period)
        top.addSpacing(6)
        top.addWidget(self.btn_prev)
        top.addWidget(self.lbl_month)
        top.addWidget(self.btn_next)
        top.addWidget(self.btn_today)
        top.addWidget(self.btn_refresh)
        top.addSpacing(10)
        top.addWidget(self.lbl_summary, 0, Qt.AlignmentFlag.AlignRight)

        # ── таблица ────────────────────────────────────────────────────────
        self.tbl = QTableWidget()
        self.tbl.setObjectName("windowsTable")
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setShowGrid(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setWordWrap(True)
        self.tbl.itemDoubleClicked.connect(self._on_double_click)

        hdr = self.tbl.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        hint = QLabel(
            "Свободное время рассчитывается автоматически: из окна работы объекта "
            "вычитаются все занятия. Периоды берутся из настроек учреждения."
        )
        hint.setObjectName("scheduleMeta")
        hint.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 6, 12, 8)
        bottom.addWidget(hint, 1)
        root.addLayout(bottom)

        self._update_period_label()

    # ── публичный API ──────────────────────────────────────────────────────

    def set_org(self, org_id: Optional[int], work_start: time, work_end: time) -> None:
        self._work_start = work_start
        self._work_end = work_end

        org_changed = (self._org_id != org_id)
        self._org_id = org_id

        if org_id is None:
            self._venues = []
            self._units = []
            self.cmb_venue.blockSignals(True)
            self.cmb_venue.clear()
            self.cmb_venue.blockSignals(False)
            self.cmb_unit.blockSignals(True)
            self.cmb_unit.clear()
            self.cmb_unit.blockSignals(False)
            self.tbl.setRowCount(0)
            self.lbl_summary.setText("Нет доступных объектов")
            return

        if org_changed:
            self._load_venues()
            self._parts = build_day_parts(get_day_safe(org_id))

        self._on_venue_changed()

    def period_mode(self) -> str:
        return str(self.cmb_period.currentData() or "day")

    def current_venue_id(self) -> Optional[int]:
        data = self.cmb_venue.currentData()
        return int(data) if data is not None else None

    def current_unit_id(self) -> Optional[int]:
        data = self.cmb_unit.currentData()
        return int(data) if data is not None else None

    def set_anchor(self, day: date) -> None:
        self._anchor = day
        self._update_period_label()
        self.reload()

    # ── загрузка справочников ──────────────────────────────────────────────

    def _load_venues(self) -> None:
        self.cmb_venue.blockSignals(True)
        self.cmb_venue.clear()
        try:
            self._venues = list(ref_service.list_active_venues(int(self._org_id)))
        except Exception:
            self._venues = []
        for v in self._venues:
            self.cmb_venue.addItem(v.name, int(v.id))
        self.cmb_venue.blockSignals(False)

    def _on_venue_changed(self, *_) -> None:
        venue_id = self.current_venue_id()

        self.cmb_unit.blockSignals(True)
        self.cmb_unit.clear()
        self.cmb_unit.addItem("Все площадки", None)
        self._units = []
        if venue_id is not None:
            try:
                self._units = list_venue_units(int(venue_id), include_inactive=False)
            except Exception:
                self._units = []
            for u in self._units:
                self.cmb_unit.addItem(u.name, int(u.id))
        self.cmb_unit.blockSignals(False)

        self.reload()

    # ── навигация ──────────────────────────────────────────────────────────

    def _update_period_label(self) -> None:
        mode = self.period_mode()

        if mode == "day":
            self.lbl_month.setText(self._anchor.strftime("%d.%m.%Y"))
            return

        if mode == "week":
            start = self._anchor - timedelta(days=self._anchor.weekday())
            end = start + timedelta(days=6)
            self.lbl_month.setText(
                f"{start.strftime('%d.%m')} – {end.strftime('%d.%m.%Y')}"
            )
            return

        self.lbl_month.setText(
            f"{MONTHS_NOM[self._anchor.month - 1]} {self._anchor.year}"
        )

    def _shift(self, delta: int) -> None:
        mode = self.period_mode()
        if mode == "day":
            self._anchor += timedelta(days=delta)
        elif mode == "week":
            self._anchor += timedelta(days=7 * delta)
        else:
            month_index = (self._anchor.year * 12 + (self._anchor.month - 1)) + delta
            year, month0 = divmod(month_index, 12)
            self._anchor = date(year, month0 + 1, 1)

        self._update_period_label()
        self.reload()

    def _go_today(self) -> None:
        self._anchor = date.today()
        self._update_period_label()
        self.reload()

    # ── расчёт и отрисовка ─────────────────────────────────────────────────

    def reload(self) -> None:
        mode = self.period_mode()
        self._update_period_label()

        venue_id = self.current_venue_id()
        if self._org_id is None or venue_id is None:
            self.tbl.setRowCount(0)
            self.tbl.setColumnCount(0)
            self.lbl_summary.setText("Нет доступных объектов" if venue_id is None else "")
            return

        days = period_days(self._anchor, mode)
        unit_id = self.current_unit_id()

        start_dt = datetime.combine(days[0], time.min, tzinfo=APP_TZ)
        end_dt = datetime.combine(days[-1] + timedelta(days=1), time.min, tzinfo=APP_TZ)

        try:
            bookings = bookings_service.list_bookings_for_range(
                [venue_id], start_dt, end_dt, include_cancelled=False
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Окна", f"Ошибка загрузки занятий:\n{e}"
            )
            bookings = []

        by_day: Dict[date, List] = {}
        for b in bookings:
            by_day.setdefault(b.starts_at.astimezone(APP_TZ).date(), []).append(b)

        self._build_table(days, by_day, unit_id, mode)

    def _build_table(
        self,
        days: Sequence[date],
        by_day: Dict[date, List],
        unit_id: Optional[int],
        mode: str,
    ) -> None:
        headers = ["Дата", "День"]
        for key, p_start, p_end in self._parts:
            title = {"morning": "Утро", "day": "День", "evening": "Вечер"}.get(key, key)
            headers.append(f"{title} · {p_start.strftime('%H:%M')}–{p_end.strftime('%H:%M')}")
        headers.append("Итого")

        self.tbl.clear()
        self.tbl.setColumnCount(len(headers))
        self.tbl.setHorizontalHeaderLabels(headers)
        self.tbl.setRowCount(len(days))

        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(2, len(headers) - 1):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.ResizeToContents)

        total_all = 0
        days_with_free = 0

        for row, day in enumerate(days):
            free = free_intervals_for_day(
                day,
                self._work_start,
                self._work_end,
                by_day.get(day, []),
                venue_unit_id=unit_id,
            )
            parts = split_by_parts(free, self._parts)

            day_total = sum(i.minutes for items in parts.values() for i in items)
            total_all += day_total
            if day_total > 0:
                days_with_free += 1

            weekend = day.weekday() >= 5
            today = day == date.today()

            it_date = QTableWidgetItem(day.strftime("%d.%m"))
            it_date.setData(Qt.ItemDataRole.UserRole, day)
            if today:
                it_date.setForeground(QColor(147, 197, 253))
            elif weekend:
                it_date.setForeground(QColor(226, 232, 240, 170))
            self.tbl.setItem(row, 0, it_date)

            it_wd = QTableWidgetItem(WEEKDAYS_SHORT[day.weekday()])
            it_wd.setData(Qt.ItemDataRole.UserRole, day)
            if today:
                it_wd.setForeground(QColor(147, 197, 253))
            elif weekend:
                it_wd.setForeground(QColor(226, 232, 240, 170))
            self.tbl.setItem(row, 1, it_wd)

            for col, (key, _s, _e) in enumerate(self._parts, start=2):
                items = parts.get(key, [])
                minutes = sum(i.minutes for i in items)

                if mode == "month":
                    text = format_duration(minutes) if minutes else "—"
                else:
                    text = format_duration(minutes) if minutes else "—"
                    detail = format_intervals(items)
                    if detail:
                        text = f"{text}\n{detail}"

                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, day)
                cell.setToolTip(
                    format_intervals(items) if items else "Свободного времени нет"
                )
                if minutes:
                    cell.setForeground(QColor(134, 239, 172))
                else:
                    cell.setForeground(QColor(226, 232, 240, 110))
                self.tbl.setItem(row, col, cell)

            it_total = QTableWidgetItem(format_duration(day_total))
            it_total.setData(Qt.ItemDataRole.UserRole, day)
            it_total.setToolTip(
                "Всего свободно" if day_total else "Свободного времени нет"
            )
            it_total.setForeground(
                QColor(255, 255, 255, 235) if day_total else QColor(226, 232, 240, 110)
            )
            self.tbl.setItem(row, len(headers) - 1, it_total)

        self.tbl.resizeRowsToContents()

        total_hours = total_all // 60
        self.lbl_summary.setText(
            f"Свободно: {total_hours} ч {total_all % 60} мин · "
            f"дней со свободным временем: {days_with_free} из {len(days)}"
        )

    def _on_double_click(self, item) -> None:
        day = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(day, date):
            self.requestOpenDay.emit(day)


def get_day_safe(org_id: Optional[int]):
    """Настройки периодов; при ошибке — значения по умолчанию из ТЗ."""
    try:
        return get_day_parts_settings(int(org_id) if org_id is not None else None)
    except Exception:
        return None


__all__ = [
    "ScheduleWindowsView",
    "Interval",
    "merge_intervals",
    "subtract_intervals",
    "split_by_parts",
    "free_intervals_for_day",
    "format_duration",
    "period_days",
]
