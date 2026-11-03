# app/ui/schedule_month_view.py
"""
Месячная визуализация расписания объекта (ТЗ, п. 6 и п. 7).

Экран показывает выбранный объект за месяц целиком: слева — дни, сверху — время,
внутри — занятия ПД и ГЗ, взятые из существующих бронирований.

Модуль только читает данные. Он не создаёт, не изменяет и не отменяет занятия,
поэтому может быть подключён к рабочей базе без риска для правил расписания.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.services import bookings_service, ref_service
from app.services.users_service import AuthUser

APP_TZ = timezone(timedelta(hours=3))

DATE_COL_W = 134
HEADER_H = 36
HOUR_W = 88
HOUR_W_MIN = 56
HOUR_W_MAX = 168
LANE_H = 26
DAY_PAD = 5
DAY_GAP = 8
SCROLL_STEP = 24

WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_NOM = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)

_BG = QColor(11, 18, 32)
_BAND_EVEN = QColor(15, 22, 36)
_BAND_ODD = QColor(12, 18, 30)
_WEEKEND_TINT = QColor(255, 255, 255, 7)
_TODAY_TINT = QColor(99, 102, 241, 30)
_GRID_LINE = QColor(255, 255, 255, 14)
_GRID_LINE_MINOR = QColor(255, 255, 255, 7)
_TEXT_DIM = QColor(226, 232, 240, 150)
_TEXT_MAIN = QColor(255, 255, 255, 236)
_ACCENT = QColor(99, 102, 241)

_KIND_PD = QColor(96, 165, 250)
_KIND_GZ = QColor(245, 158, 11)
_KIND_CANCELLED = QColor(148, 163, 184)


# ──────────────────────────────────────────────────────────────────────────────
# геометрия
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DayGeom:
    day: date
    top: int
    height: int
    lanes: int


@dataclass(frozen=True)
class MonthGeometry:
    days: Tuple[DayGeom, ...]
    hour_w: int
    start_min: int
    end_min: int
    lane_h: int
    day_pad: int

    @property
    def px_per_min(self) -> float:
        return self.hour_w / 60.0

    @property
    def body_width(self) -> int:
        return max(1, int(round((self.end_min - self.start_min) * self.px_per_min)))

    @property
    def total_height(self) -> int:
        if not self.days:
            return 0
        last = self.days[-1]
        return last.top + last.height

    def x_for(self, dt: datetime) -> float:
        local = dt.astimezone(APP_TZ)
        minutes = local.hour * 60 + local.minute + local.second / 60.0
        return (minutes - self.start_min) * self.px_per_min


def assign_lanes(bookings: Sequence) -> List[List[object]]:
    """
    Раскладывает занятия одного дня по дорожкам так, чтобы одновременные
    группы не перекрывали друг друга. Возвращает список дорожек.
    """
    lanes: List[List[object]] = []
    ordered = sorted(bookings, key=lambda b: (b.starts_at, b.ends_at))
    for b in ordered:
        placed = False
        for lane in lanes:
            if lane[-1].ends_at <= b.starts_at:
                lane.append(b)
                placed = True
                break
        if not placed:
            lanes.append([b])
    return lanes


def build_geometry(
    days: Sequence[date],
    lanes_by_day: Dict[date, List[List[object]]],
    *,
    hour_w: int = HOUR_W,
    start_min: int = 8 * 60,
    end_min: int = 22 * 60,
    lane_h: int = LANE_H,
    day_pad: int = DAY_PAD,
    day_gap: int = DAY_GAP,
) -> MonthGeometry:
    if end_min <= start_min:
        end_min = start_min + 60

    out: List[DayGeom] = []
    top = 0
    for d in days:
        lane_count = max(1, len(lanes_by_day.get(d, [])))
        height = lane_count * lane_h + 2 * day_pad
        out.append(DayGeom(day=d, top=top, height=height, lanes=lane_count))
        top += height + day_gap

    return MonthGeometry(
        days=tuple(out),
        hour_w=hour_w,
        start_min=start_min,
        end_min=end_min,
        lane_h=lane_h,
        day_pad=day_pad,
    )


def month_bounds(anchor: date) -> Tuple[date, date]:
    first = anchor.replace(day=1)
    next_month = (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    )
    return first, next_month - timedelta(days=1)


def month_days(anchor: date) -> List[date]:
    first, last = month_bounds(anchor)
    out: List[date] = []
    cur = first
    while cur <= last:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def shift_month(anchor: date, delta: int) -> date:
    month_index = (anchor.year * 12 + (anchor.month - 1)) + int(delta)
    year, month0 = divmod(month_index, 12)
    return date(year, month0 + 1, 1)


# ──────────────────────────────────────────────────────────────────────────────
# цвета занятий
# ──────────────────────────────────────────────────────────────────────────────

def booking_base_color(b, free_gz_ids: Optional[Iterable[int]] = None) -> QColor:
    status = (getattr(b, "status", "") or "").lower()
    if status == "cancelled":
        return QColor(_KIND_CANCELLED)

    kind = (getattr(b, "kind", "") or "").upper()
    if kind == "GZ":
        base = QColor(_KIND_GZ)
        gid = getattr(b, "gz_group_id", None)
        if gid is not None and free_gz_ids and int(gid) in set(free_gz_ids):
            base = base.lighter(115).lighter(115)
        return base
    if kind == "PD":
        return QColor(_KIND_PD)
    return QColor(148, 163, 184)


def booking_display_name(b) -> str:
    name = (getattr(b, "tenant_name", "") or "").strip()
    if not name:
        name = (getattr(b, "gz_group_name", "") or "").strip()
    if not name:
        name = (getattr(b, "title", "") or "").strip()
    return name or "Без названия"


def booking_time_text(b) -> str:
    s = b.starts_at.astimezone(APP_TZ)
    e = b.ends_at.astimezone(APP_TZ)
    return f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')}"


# ──────────────────────────────────────────────────────────────────────────────
# шапка со временем
# ──────────────────────────────────────────────────────────────────────────────

class _MonthTimeHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom: Optional[MonthGeometry] = None
        self._offset = 0
        self.setFixedHeight(HEADER_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_geometry(self, geom: Optional[MonthGeometry]) -> None:
        self._geom = geom
        self.update()

    def set_offset(self, offset: int) -> None:
        if self._offset == offset:
            return
        self._offset = int(offset)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(_BG))

        geom = self._geom
        if geom is None:
            return

        p.setClipRect(self.rect())
        f = QFont(self.font())
        f.setPointSizeF(max(f.pointSizeF(), 8.5))
        f.setBold(True)
        p.setFont(f)

        hour = geom.start_min // 60
        last_hour = (geom.end_min + 59) // 60
        while hour <= last_hour:
            x = (hour * 60 - geom.start_min) * geom.px_per_min - self._offset
            if x < -60 or x > geom.body_width + 60:
                hour += 1
                continue
            p.setPen(QPen(QColor(255, 255, 255, 30), 1))
            p.drawLine(int(x), HEADER_H - 8, int(x), HEADER_H)
            p.setPen(QPen(_TEXT_DIM))
            p.drawText(
                QRectF(x - 30, 8, 60, HEADER_H - 18),
                Qt.AlignmentFlag.AlignCenter,
                f"{hour:02d}:00",
            )
            hour += 1

        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.drawLine(0, HEADER_H - 1, self.width(), HEADER_H - 1)


# ──────────────────────────────────────────────────────────────────────────────
# левая колонка с датами
# ──────────────────────────────────────────────────────────────────────────────

class _MonthDateColumn(QWidget):
    ROLE_NONE = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom: Optional[MonthGeometry] = None
        self._counts: Dict[date, int] = {}
        self._offset = 0
        self.setFixedWidth(DATE_COL_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def set_geometry(self, geom: Optional[MonthGeometry], counts: Dict[date, int]) -> None:
        self._geom = geom
        self._counts = counts or {}
        self.update()

    def set_offset(self, offset: int) -> None:
        if self._offset == offset:
            return
        self._offset = int(offset)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(_BG))

        geom = self._geom
        if geom is None:
            return

        p.setClipRect(self.rect())
        today = date.today()

        for dg in geom.days:
            y = dg.top - self._offset
            if y + dg.height < -20 or y > self.height() + 20:
                continue

            rect = QRectF(2, y + 1, DATE_COL_W - 8, dg.height - 2)
            weekend = dg.day.weekday() >= 5
            if dg.day == today:
                p.setBrush(QColor(99, 102, 241, 34))
                p.setPen(QPen(QColor(99, 102, 241, 130), 1))
                p.drawRoundedRect(rect, 8, 8)
                p.setPen(QPen(QColor(99, 102, 241, 220), 3))
                p.drawLine(2, int(y + 6), 2, int(y + dg.height - 6))
            elif weekend:
                p.setBrush(QColor(255, 255, 255, 5))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(rect, 8, 8)

            num_font = QFont(self.font())
            num_font.setPointSizeF(max(num_font.pointSizeF(), 12.0))
            num_font.setBold(True)
            p.setFont(num_font)
            p.setPen(QPen(_TEXT_MAIN if dg.day == today else QColor(255, 255, 255, 220)))
            p.drawText(
                QRectF(14, y + 4, DATE_COL_W - 24, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{dg.day.day:02d}",
            )

            wd_font = QFont(self.font())
            wd_font.setPointSizeF(max(wd_font.pointSizeF(), 8.5))
            wd_font.setBold(False)
            p.setFont(wd_font)
            p.setPen(QPen(QColor(226, 232, 240, 165)))
            p.drawText(
                QRectF(14, y + 22, DATE_COL_W - 24, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                WEEKDAYS_SHORT[dg.day.weekday()],
            )

            count = self._counts.get(dg.day, 0)
            if count:
                p.setPen(QPen(QColor(226, 232, 240, 120)))
                p.drawText(
                    QRectF(14, y + dg.height - 18, DATE_COL_W - 24, 16),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    f"{count} зан.",
                )

        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawLine(DATE_COL_W - 1, 0, DATE_COL_W - 1, self.height())


# ──────────────────────────────────────────────────────────────────────────────
# сетка занятий
# ──────────────────────────────────────────────────────────────────────────────

class _MonthGrid(QWidget):
    bookingActivated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._geom: Optional[MonthGeometry] = None
        self._lanes: Dict[date, List[List[object]]] = {}
        self._free_gz_ids: set[int] = set()
        self._selected_id: Optional[int] = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_data(
        self,
        geom: Optional[MonthGeometry],
        lanes: Dict[date, List[List[object]]],
        free_gz_ids: Optional[Iterable[int]] = None,
    ) -> None:
        self._geom = geom
        self._lanes = lanes or {}
        self._free_gz_ids = set(int(x) for x in (free_gz_ids or []))
        if geom is None:
            self.setFixedSize(1, 1)
        else:
            self.setFixedSize(geom.body_width, max(1, geom.total_height))
        self.update()

    # ── отрисовка ───────────────────────────────────────────────────────────

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), _BG)

        geom = self._geom
        if geom is None:
            return

        today = date.today()

        for index, dg in enumerate(geom.days):
            band = QRectF(0, dg.top, self.width(), dg.height)

            p.fillRect(band, _BAND_EVEN if index % 2 == 0 else _BAND_ODD)
            if dg.day.weekday() >= 5:
                p.fillRect(band, _WEEKEND_TINT)
            if dg.day == today:
                p.fillRect(band, _TODAY_TINT)

            # сетка времени
            hour = geom.start_min // 60
            while hour * 60 <= geom.end_min:
                x = (hour * 60 - geom.start_min) * geom.px_per_min
                p.setPen(QPen(_GRID_LINE, 1))
                p.drawLine(int(x), int(dg.top), int(x), int(dg.top + dg.height))
                half = x + 30 * geom.px_per_min
                p.setPen(QPen(_GRID_LINE_MINOR, 1))
                p.drawLine(int(half), int(dg.top), int(half), int(dg.top + dg.height))
                hour += 1

            # дорожки
            lanes = self._lanes.get(dg.day, [])
            for lane_index, lane in enumerate(lanes):
                for b in lane:
                    self._paint_booking(p, geom, dg, b, lane_index)

            p.setPen(QPen(QColor(255, 255, 255, 16), 1))
            p.drawLine(0, int(dg.top + dg.height), self.width(), int(dg.top + dg.height))

    def _paint_booking(self, p: QPainter, geom: MonthGeometry, dg: DayGeom, b, lane_index: int) -> None:
        start = b.starts_at.astimezone(APP_TZ)
        end = b.ends_at.astimezone(APP_TZ)
        day_start = datetime.combine(dg.day, time.min, tzinfo=APP_TZ)
        day_end = day_start + timedelta(days=1)

        s = max(start, day_start)
        e = min(end, day_end)
        if e <= s:
            return

        x0 = geom.x_for(s)
        x1 = geom.x_for(e)
        width = max(6.0, x1 - x0)

        y = dg.top + geom.day_pad + lane_index * geom.lane_h
        rect = QRectF(x0 + 1.0, y + 1.0, width - 2.0, geom.lane_h - 3.0)

        base = booking_base_color(b, self._free_gz_ids)
        cancelled = (getattr(b, "status", "") or "").lower() == "cancelled"

        fill = QColor(base).darker(190)
        fill.setAlpha(255)
        border = QColor(base).darker(120)

        path_rect = rect.adjusted(0, 0, 0, 0)
        p.setBrush(fill)
        p.setPen(QPen(border, 1.2, Qt.PenStyle.DashLine if cancelled else Qt.PenStyle.SolidLine))
        p.drawRoundedRect(path_rect, 7, 7)

        # цветовой акцент слева
        accent = QRectF(rect.left(), rect.top() + 2, 3.0, rect.height() - 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(base if not cancelled else QColor(_KIND_CANCELLED))
        p.drawRoundedRect(accent, 1.5, 1.5)

        if self._selected_id is not None and int(getattr(b, "id", 0)) == self._selected_id:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 210), 1.6))
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)

        # текст
        p.setClipRect(rect.adjusted(2, 0, -2, 0))
        text_rect = QRectF(rect.left() + 8, rect.top() + 1, max(0.0, rect.width() - 12), rect.height() - 2)

        name_font = QFont(self.font())
        name_font.setPointSizeF(max(name_font.pointSizeF(), 8.5))
        name_font.setBold(True)
        p.setFont(name_font)
        p.setPen(QPen(QColor(255, 255, 255, 235) if not cancelled else QColor(226, 232, 240, 170)))

        fm = QFontMetrics(name_font)
        label = booking_display_name(b)
        if rect.height() > 30 and rect.width() > 110:
            p.drawText(
                QRectF(text_rect.left(), text_rect.top(), text_rect.width(), 15),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fm.elidedText(label, Qt.TextElideMode.ElideRight, int(text_rect.width())),
            )
            small = QFont(self.font())
            small.setPointSizeF(max(small.pointSizeF(), 7.5))
            small.setBold(False)
            p.setFont(small)
            p.setPen(QPen(QColor(226, 232, 240, 150)))
            p.drawText(
                QRectF(text_rect.left(), text_rect.top() + 14, text_rect.width(), 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                booking_time_text(b),
            )
        else:
            p.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fm.elidedText(label, Qt.TextElideMode.ElideRight, int(text_rect.width())),
            )

        p.setClipping(False)

    # ── взаимодействие ──────────────────────────────────────────────────────

    def _hit(self, pos) -> Tuple[Optional[object], Optional[DayGeom]]:
        geom = self._geom
        if geom is None:
            return None, None

        x = pos.x()
        y = pos.y()

        for dg in geom.days:
            if not (dg.top <= y <= dg.top + dg.height):
                continue
            for lane_index, lane in enumerate(self._lanes.get(dg.day, [])):
                top = dg.top + geom.day_pad + lane_index * geom.lane_h
                if not (top <= y <= top + geom.lane_h):
                    continue
                for b in lane:
                    start = b.starts_at.astimezone(APP_TZ)
                    end = b.ends_at.astimezone(APP_TZ)
                    day_start = datetime.combine(dg.day, time.min, tzinfo=APP_TZ)
                    day_end = day_start + timedelta(days=1)
                    s = max(start, day_start)
                    e = min(end, day_end)
                    if e <= s:
                        continue
                    x0 = geom.x_for(s)
                    x1 = geom.x_for(e)
                    if x0 - 2 <= x <= x1 + 2:
                        return b, dg
            return None, dg
        return None, None

    def mouseMoveEvent(self, event) -> None:
        b, dg = self._hit(event.position().toPoint())
        if b is not None:
            kind = "ГЗ" if (getattr(b, "kind", "") or "").upper() == "GZ" else "ПД"
            status = "Отменено" if (getattr(b, "status", "") or "").lower() == "cancelled" else "Запланировано"
            tip = (
                f"{booking_display_name(b)}\n"
                f"{dg.day.strftime('%d.%m.%Y') if dg else ''} · {booking_time_text(b)}\n"
                f"{kind} · {status}"
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            from PySide6.QtWidgets import QToolTip
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            b, _dg = self._hit(event.position().toPoint())
            self._selected_id = int(getattr(b, "id", 0)) if b is not None else None
            self.update()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            b, _dg = self._hit(event.position().toPoint())
            if b is not None:
                self.bookingActivated.emit(b)
        super().mouseDoubleClickEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# карточка занятия
# ──────────────────────────────────────────────────────────────────────────────

class MonthBookingDetails(QDialog):
    """Краткая информация о занятии с переходом к контрагенту и к дню."""

    def __init__(self, parent, booking, *, can_open_tenant: bool):
        super().__init__(parent)
        self.setObjectName("dialog")
        self._booking = booking
        self.open_tenant_requested = False
        self.open_day_requested = False

        self.setWindowTitle("Занятие")
        self.setModal(True)
        self.setMinimumWidth(460)

        kind = "ГЗ" if (getattr(booking, "kind", "") or "").upper() == "GZ" else "ПД"
        status = "Отменено" if (getattr(booking, "status", "") or "").lower() == "cancelled" else "Запланировано"
        day = booking.starts_at.astimezone(APP_TZ)

        rows = [
            ("Дата", day.strftime("%d.%m.%Y") + f" ({WEEKDAYS_SHORT[day.weekday()]})"),
            ("Время", booking_time_text(booking)),
            ("Тип", kind),
            ("Название", booking_display_name(booking)),
            ("Площадка", (getattr(booking, "venue_unit_name", "") or "—")),
            ("Статус", status),
        ]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(8)

        title = QLabel(booking_display_name(booking))
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        lay.addWidget(title)

        for caption, value in rows:
            line = QLabel(f"{caption}: {value}")
            line.setWordWrap(True)
            lay.addWidget(line)

        buttons = QDialogButtonBox(self)
        if can_open_tenant and kind == "ПД" and getattr(booking, "tenant_id", None):
            btn_tenant = QPushButton("Открыть карточку контрагента")
            btn_tenant.clicked.connect(self._on_tenant)
            buttons.addButton(btn_tenant, QDialogButtonBox.ButtonRole.ActionRole)

        btn_day = QPushButton("Показать этот день")
        btn_day.clicked.connect(self._on_day)
        buttons.addButton(btn_day, QDialogButtonBox.ButtonRole.ActionRole)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.reject)
        buttons.addButton(btn_close, QDialogButtonBox.ButtonRole.RejectRole)
        lay.addWidget(buttons)

    def _on_tenant(self) -> None:
        self.open_tenant_requested = True
        self.accept()

    def _on_day(self) -> None:
        self.open_day_requested = True
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# экран месяца
# ──────────────────────────────────────────────────────────────────────────────

class ScheduleMonthView(QWidget):
    """
    Публичный API для страницы расписания:

        view.set_org(org_id, work_start, work_end)
        view.set_show_cancelled(flag)
        view.set_free_gz_ids(ids)
        view.reload()
    """

    requestOpenTenant = Signal(int)
    requestOpenDay = Signal(object)

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("monthView")
        self.user = user

        self._org_id: Optional[int] = None
        self._work_start = time(8, 0)
        self._work_end = time(22, 0)
        self._show_cancelled = False
        self._free_gz_ids: set[int] = set()
        self._rebuilding = False

        self._anchor: date = date.today().replace(day=1)
        self._venues: List = []
        self._lanes: Dict[date, List[List[object]]] = {}
        self._counts: Dict[date, int] = {}
        self._geom: Optional[MonthGeometry] = None

        # ── панель управления ──────────────────────────────────────────────
        self.lbl_venue = QLabel("Объект:")
        self.cmb_venue = QComboBox()
        self.cmb_venue.setMinimumWidth(220)
        self.cmb_venue.currentIndexChanged.connect(lambda *_: self.reload())

        self.btn_prev = QToolButton()
        self.btn_prev.setText("◀")
        self.btn_prev.setObjectName("monthNav")
        self.btn_prev.setToolTip("Предыдущий месяц")
        self.btn_prev.clicked.connect(lambda: self._shift(-1))

        self.btn_next = QToolButton()
        self.btn_next.setText("▶")
        self.btn_next.setObjectName("monthNav")
        self.btn_next.setToolTip("Следующий месяц")
        self.btn_next.clicked.connect(lambda: self._shift(1))

        self.lbl_month = QLabel("")
        self.lbl_month.setObjectName("monthTitle")
        self.lbl_month.setMinimumWidth(190)
        self.lbl_month.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_today = QPushButton("Текущий месяц")
        self.btn_today.clicked.connect(self._go_today)

        self.cb_cancelled = QCheckBox("Отменённые")
        self.cb_cancelled.stateChanged.connect(self._on_cancelled_changed)

        legend = QHBoxLayout()
        legend.setSpacing(10)
        legend.addWidget(self._legend_item("ПД", _KIND_PD))
        legend.addWidget(self._legend_item("ГЗ", _KIND_GZ))
        legend.addWidget(self._legend_item("Отменено", _KIND_CANCELLED))

        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("scheduleMeta")

        top = QHBoxLayout()
        top.setContentsMargins(12, 10, 12, 6)
        top.setSpacing(8)
        top.addWidget(self.lbl_venue)
        top.addWidget(self.cmb_venue, 1)
        top.addSpacing(8)
        top.addWidget(self.btn_prev)
        top.addWidget(self.lbl_month)
        top.addWidget(self.btn_next)
        top.addWidget(self.btn_today)
        top.addSpacing(12)
        top.addWidget(self.cb_cancelled)
        top.addSpacing(8)
        top.addLayout(legend)
        top.addSpacing(8)
        top.addWidget(self.lbl_summary, 0, Qt.AlignmentFlag.AlignRight)

        # ── сетка ──────────────────────────────────────────────────────────
        self.time_header = _MonthTimeHeader(self)

        corner = QWidget(self)
        corner.setFixedWidth(DATE_COL_W)
        corner.setFixedHeight(HEADER_H)
        corner_lay = QHBoxLayout(corner)
        corner_lay.setContentsMargins(12, 0, 4, 0)
        lbl_corner = QLabel("Дата")
        lbl_corner.setObjectName("scheduleMetaStrong")
        corner_lay.addWidget(lbl_corner)
        corner_lay.addStretch(1)

        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(0)
        header_lay.addWidget(corner)
        header_lay.addWidget(self.time_header, 1)

        self.date_col = _MonthDateColumn(self)

        self.grid = _MonthGrid(self)
        self.grid.bookingActivated.connect(self._on_booking_activated)

        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.grid)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.time_header.set_offset)
        self.scroll.verticalScrollBar().valueChanged.connect(self.date_col.set_offset)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.date_col)
        body.addWidget(self.scroll, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addLayout(header_lay)
        root.addLayout(body, 1)

        self._update_month_label()
        self._apply_empty_state()

    # ── вспомогательное ────────────────────────────────────────────────────

    def _legend_item(self, text: str, color: QColor) -> QWidget:
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        chip = QLabel()
        chip.setFixedSize(10, 10)
        chip.setStyleSheet(
            f"background: rgb({color.red()},{color.green()},{color.blue()});"
            "border-radius:3px;"
        )
        lbl = QLabel(text)
        lbl.setObjectName("scheduleMeta")

        lay.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        return w

    def _update_month_label(self) -> None:
        self.lbl_month.setText(f"{MONTHS_NOM[self._anchor.month - 1]} {self._anchor.year}")

    def _apply_empty_state(self) -> None:
        has_venue = self.cmb_venue.count() > 0
        self.scroll.setVisible(has_venue)
        self.date_col.setVisible(has_venue)
        if not has_venue:
            self.lbl_summary.setText("Нет доступных объектов")

    def _shift(self, delta: int) -> None:
        self._anchor = shift_month(self._anchor, delta)
        self._update_month_label()
        self.reload()

    def _go_today(self) -> None:
        self._anchor = date.today().replace(day=1)
        self._update_month_label()
        self.reload()

    def _on_cancelled_changed(self, *_):
        self._show_cancelled = self.cb_cancelled.isChecked()
        self.reload()

    # ── публичный API ──────────────────────────────────────────────────────

    def set_org(self, org_id: Optional[int], work_start: time, work_end: time) -> None:
        self._work_start = work_start
        self._work_end = work_end

        org_changed = (self._org_id != org_id)
        self._org_id = org_id

        if org_id is None:
            self._venues = []
            self.cmb_venue.blockSignals(True)
            self.cmb_venue.clear()
            self.cmb_venue.blockSignals(False)
            self._lanes = {}
            self._counts = {}
            self.rebuild()
            return

        if org_changed:
            self._load_venues()

        self.reload()

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
        self._apply_empty_state()

    def set_show_cancelled(self, flag: bool) -> None:
        if self.cb_cancelled.isChecked() != bool(flag):
            self.cb_cancelled.blockSignals(True)
            self.cb_cancelled.setChecked(bool(flag))
            self.cb_cancelled.blockSignals(False)
        self._show_cancelled = bool(flag)

    def set_free_gz_ids(self, ids: Iterable[int]) -> None:
        self._free_gz_ids = set(int(x) for x in (ids or []))

    def current_venue_id(self) -> Optional[int]:
        data = self.cmb_venue.currentData()
        return int(data) if data is not None else None

    def reload(self) -> None:
        venue_id = self.current_venue_id()
        if self._org_id is None or venue_id is None:
            self._lanes = {}
            self._counts = {}
            self.rebuild()
            return

        first, last = month_bounds(self._anchor)
        start_dt = datetime.combine(first, time.min, tzinfo=APP_TZ)
        end_dt = datetime.combine(last + timedelta(days=1), time.min, tzinfo=APP_TZ)

        try:
            bookings = bookings_service.list_bookings_for_range(
                [venue_id], start_dt, end_dt, include_cancelled=self._show_cancelled
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Расписание",
                f"Ошибка загрузки занятий за месяц:\n{e}",
            )
            bookings = []

        lanes_by_day: Dict[date, List[List[object]]] = {}
        by_day: Dict[date, List[object]] = {}
        for b in bookings:
            local_day = b.starts_at.astimezone(APP_TZ).date()
            by_day.setdefault(local_day, []).append(b)

        for d, items in by_day.items():
            lanes_by_day[d] = assign_lanes(items)

        self._lanes = lanes_by_day
        self._counts = {d: len(items) for d, items in by_day.items()}
        self.rebuild()

    def rebuild(self) -> None:
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            self._rebuild_impl()
        finally:
            self._rebuilding = False

    def _rebuild_impl(self) -> None:
        days = month_days(self._anchor)

        start_min = self._work_start.hour * 60 + self._work_start.minute
        end_min = self._work_end.hour * 60 + self._work_end.minute
        if end_min <= start_min:
            end_min = min(24 * 60, start_min + 60)

        # ширина часа подбирается так, чтобы рабочий день занимал окно целиком
        hour_w = HOUR_W
        avail = self.scroll.viewport().width()
        span_hours = (end_min - start_min) / 60.0
        if avail > 40 and span_hours > 0:
            hour_w = int(max(HOUR_W_MIN, min(HOUR_W_MAX, avail / span_hours)))

        geom = build_geometry(
            days,
            self._lanes,
            hour_w=hour_w,
            start_min=start_min,
            end_min=end_min,
        )
        self._geom = geom

        self.grid.set_data(geom, self._lanes, self._free_gz_ids)
        self.time_header.set_geometry(geom)
        self.time_header.set_offset(self.scroll.horizontalScrollBar().value())
        self.date_col.set_geometry(geom, self._counts)
        self.date_col.set_offset(self.scroll.verticalScrollBar().value())

        total = sum(self._counts.values())
        pd_count = 0
        gz_count = 0
        for items in self._lanes.values():
            for lane in items:
                for b in lane:
                    if (getattr(b, "kind", "") or "").upper() == "GZ":
                        gz_count += 1
                    else:
                        pd_count += 1
        self.lbl_summary.setText(f"ПД: {pd_count} · ГЗ: {gz_count} · всего: {total}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._geom is not None and not self._rebuilding:
            self.rebuild()

    # ── события ────────────────────────────────────────────────────────────

    def _can_open_tenant_card(self) -> bool:
        role = (getattr(self.user, "role_code", "") or "").lower()
        if role == "admin":
            return True
        return "tab.tenants" in (getattr(self.user, "permissions", set()) or set())

    def _on_booking_activated(self, booking) -> None:
        dlg = MonthBookingDetails(
            self, booking, can_open_tenant=self._can_open_tenant_card()
        )
        dlg.exec()

        if dlg.open_tenant_requested and getattr(booking, "tenant_id", None):
            self.requestOpenTenant.emit(int(booking.tenant_id))
        elif dlg.open_day_requested:
            self.requestOpenDay.emit(booking.starts_at.astimezone(APP_TZ).date())
