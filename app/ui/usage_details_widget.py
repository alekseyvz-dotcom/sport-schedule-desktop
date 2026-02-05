from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout


# Dark-friendly palette (no stylesheets)
PD_COLOR = QColor("#60a5fa")  # blue
GZ_COLOR = QColor("#f59e0b")  # amber


@dataclass(frozen=True)
class UsageTotals:
    title: str
    period_title: str

    cap_sec: int
    pd_sec: int
    gz_sec: int

    m_cap: int
    m_pd: int
    m_gz: int

    d_cap: int
    d_pd: int
    d_gz: int

    e_cap: int
    e_pd: int
    e_gz: int


def _pct(val: int, cap: int) -> float:
    return 0.0 if cap <= 0 else 100.0 * (val / cap)


def _hours(sec: int) -> float:
    return sec / 3600.0


class _BarsWidget(QWidget):
    """3 stacked bars: Утро/День/Вечер, внутри ПД+ГЗ, фон = ёмкость смены."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[UsageTotals] = None
        self._shift_titles: Tuple[str, str, str] = ("Утро", "День", "Вечер")
        self.setMinimumHeight(170)

        self._col_text = QColor(255, 255, 255, 235)
        self._col_muted = QColor(226, 232, 240, 160)
        self._col_bar_bg = QColor(255, 255, 255, 18)

    def set_data(self, data: Optional[UsageTotals]) -> None:
        self._data = data
        self.update()

    def set_shift_titles(self, morning: str, day: str, evening: str) -> None:
        self._shift_titles = (morning or "Утро", day or "День", evening or "Вечер")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.rect().adjusted(16, 14, -16, -14)

        p.setPen(QPen(self._col_muted))
        p.setFont(QFont(self.font().family(), self.font().pointSize(), QFont.Weight.DemiBold))
        p.drawText(r.x(), r.y(), "Загрузка по сменам (ПД / ГЗ)")

        if not self._data:
            p.setPen(QPen(self._col_muted))
            p.setFont(self.font())
            p.drawText(r.x(), r.y() + 28, "Выберите площадку или итог по учреждению слева.")
            return

        m_title, d_title, e_title = self._shift_titles
        rows = [
            (m_title, self._data.m_cap, self._data.m_pd, self._data.m_gz),
            (d_title, self._data.d_cap, self._data.d_pd, self._data.d_gz),
            (e_title, self._data.e_cap, self._data.e_pd, self._data.e_gz),
        ]

        y = r.y() + 42
        bar_h = 22
        gap = 18
        label_w = 160
        bar_w = max(260, r.width() - label_w - 90)

        p.setFont(self.font())

        for name, cap, pd, gz in rows:
            total = pd + gz
            pd_w = 0.0 if cap <= 0 else bar_w * (pd / cap)
            gz_w = 0.0 if cap <= 0 else bar_w * (gz / cap)
            tot_pct = _pct(total, cap)

            p.setPen(QPen(self._col_text))
            p.drawText(r.x(), y + bar_h - 4, name)

            bx = r.x() + label_w
            by = y

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._col_bar_bg)
            p.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), 8, 8)

            p.setBrush(PD_COLOR)
            p.drawRoundedRect(QRectF(bx, by, max(0.0, pd_w), bar_h), 8, 8)

            p.setBrush(GZ_COLOR)
            p.drawRoundedRect(QRectF(bx + pd_w, by, max(0.0, gz_w), bar_h), 8, 8)

            p.setPen(QPen(self._col_text))
            p.drawText(int(bx + bar_w + 10), int(y + bar_h - 4), f"{tot_pct:.1f}%")

            p.setPen(QPen(self._col_muted))
            p.drawText(int(bx), int(y - 2), f"ПД {_hours(pd):.1f}ч  ГЗ {_hours(gz):.1f}ч")

            y += bar_h + gap


class _DonutWidget(QWidget):
    """Donut: ПД / ГЗ / Свободно."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[UsageTotals] = None
        self.setMinimumHeight(210)

        self._col_text = QColor(255, 255, 255, 235)
        self._col_muted = QColor(226, 232, 240, 160)
        self._col_free = QColor(255, 255, 255, 26)
        self._col_hole = QColor(2, 6, 23, 160)

    def set_data(self, data: Optional[UsageTotals]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.rect().adjusted(16, 14, -16, -14)

        p.setPen(QPen(self._col_muted))
        p.setFont(QFont(self.font().family(), self.font().pointSize(), QFont.Weight.DemiBold))
        p.drawText(r.x(), r.y(), "Структура занятости за период")

        if not self._data or self._data.cap_sec <= 0:
            p.setPen(QPen(self._col_muted))
            p.setFont(self.font())
            p.drawText(r.x(), r.y() + 28, "Нет данных.")
            return

        cap = self._data.cap_sec
        pd = max(0, self._data.pd_sec)
        gz = max(0, self._data.gz_sec)
        busy = min(cap, pd + gz)
        free = max(0, cap - busy)

        pd_pct = _pct(pd, cap)
        gz_pct = _pct(gz, cap)
        free_pct = _pct(free, cap)

        size = min(r.width(), r.height() - 30)
        cx = r.x()
        cy = r.y() + 30
        donut = QRectF(cx, cy, size, size)

        start = 90 * 16

        def draw_slice(val_sec: int, color: QColor):
            nonlocal start
            if cap <= 0 or val_sec <= 0:
                return
            span = -int(360 * 16 * (val_sec / cap))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawPie(donut, start, span)
            start += span

        draw_slice(pd, PD_COLOR)
        draw_slice(gz, GZ_COLOR)
        draw_slice(free, self._col_free)

        p.setBrush(self._col_hole)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(donut.adjusted(size * 0.22, size * 0.22, -size * 0.22, -size * 0.22))

        p.setPen(QPen(self._col_text))
        p.setFont(QFont(self.font().family(), self.font().pointSize() + 4, QFont.Weight.Bold))
        p.drawText(donut, Qt.AlignmentFlag.AlignCenter, f"{_pct(busy, cap):.1f}%")

        lx = int(donut.right() + 18)
        ly = int(donut.top() + 10)

        p.setFont(self.font())
        p.setPen(QPen(self._col_text))
        p.drawText(lx, ly, f"ПД: {pd_pct:.1f}% ({_hours(pd):.1f}ч)")
        p.drawText(lx, ly + 22, f"ГЗ: {gz_pct:.1f}% ({_hours(gz):.1f}ч)")
        p.setPen(QPen(self._col_muted))
        p.drawText(lx, ly + 44, f"Свободно: {free_pct:.1f}% ({_hours(free):.1f}ч)")


class UsageDetailsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.lbl_title = QLabel("Детали")
        self.lbl_title.setObjectName("sectionTitle")

        self.lbl_period = QLabel("")
        self.lbl_period.setObjectName("scheduleMeta")

        self.donut = _DonutWidget(self)
        self.bars = _BarsWidget(self)

        card = QWidget(self)
        card.setObjectName("detailsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_period)
        lay.addWidget(self.donut)
        lay.addWidget(self.bars, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card, 1)

        self.set_data(None)

    def set_shift_titles(self, morning_title: str, day_title: str, evening_title: str) -> None:
        self.bars.set_shift_titles(morning_title, day_title, evening_title)

    def set_data(self, data: Optional[UsageTotals]):
        if not data:
            self.lbl_title.setText("Детали")
            self.lbl_period.setText("")
            self.set_shift_titles("Утро", "День", "Вечер")
        else:
            self.lbl_title.setText(data.title)
            self.lbl_period.setText(f"Период: {data.period_title}")

        self.donut.set_data(data)
        self.bars.set_data(data)
