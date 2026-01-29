from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame


PD_COLOR = QColor("#9bd7ff")  # ПД
GZ_COLOR = QColor("#ffcc80")  # ГЗ (оранжевый)
BG_BAR = QColor("#eef2f7")
TEXT = QColor("#0f172a")
MUTED = QColor("#475569")


@dataclass(frozen=True)
class UsageTotals:
    title: str  # "Площадка: ..." или "Учреждение: ..."
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
        self.setMinimumHeight(170)

    def set_data(self, data: Optional[UsageTotals]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.rect().adjusted(16, 14, -16, -14)

        p.setPen(QPen(MUTED))
        p.setFont(QFont(self.font().family(), self.font().pointSize(), QFont.Weight.DemiBold))
        p.drawText(r.x(), r.y(), "Загрузка по сменам (ПД / ГЗ)")

        if not self._data:
            p.setPen(QPen(MUTED))
            p.setFont(self.font())
            p.drawText(r.x(), r.y() + 28, "Выберите площадку или итог по учреждению слева.")
            return

        rows = [
            ("Утро 08–12", self._data.m_cap, self._data.m_pd, self._data.m_gz),
            ("День 12–18", self._data.d_cap, self._data.d_pd, self._data.d_gz),
            ("Вечер 18–22", self._data.e_cap, self._data.e_pd, self._data.e_gz),
        ]

        y = r.y() + 42
        bar_h = 22
        gap = 18
        label_w = 120
        bar_w = max(260, r.width() - label_w - 90)

        p.setFont(self.font())

        for name, cap, pd, gz in rows:
            total = pd + gz
            pd_w = 0 if cap <= 0 else bar_w * (pd / cap)
            gz_w = 0 if cap <= 0 else bar_w * (gz / cap)
            tot_pct = _pct(total, cap)

            # label
            p.setPen(QPen(TEXT))
            p.drawText(r.x(), y + bar_h - 4, name)

            # background bar
            bx = r.x() + label_w
            by = y
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(BG_BAR)
            p.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), 8, 8)

            # PD chunk
            p.setBrush(PD_COLOR)
            p.drawRoundedRect(QRectF(bx, by, max(0.0, pd_w), bar_h), 8, 8)

            # GZ chunk (рисуем поверх справа от PD)
            p.setBrush(GZ_COLOR)
            p.drawRoundedRect(QRectF(bx + pd_w, by, max(0.0, gz_w), bar_h), 8, 8)

            # text справа
            p.setPen(QPen(TEXT))
            p.drawText(int(bx + bar_w + 10), int(y + bar_h - 4), f"{tot_pct:.1f}%")

            # подписи маленькие
            p.setPen(QPen(MUTED))
            p.drawText(int(bx), int(y - 2), f"ПД { _hours(pd):.1f}ч  ГЗ { _hours(gz):.1f}ч")

            y += bar_h + gap


class _DonutWidget(QWidget):
    """Donut: ПД / ГЗ / Свободно."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[UsageTotals] = None
        self.setMinimumHeight(210)

    def set_data(self, data: Optional[UsageTotals]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self.rect().adjusted(16, 14, -16, -14)

        p.setPen(QPen(MUTED))
        p.setFont(QFont(self.font().family(), self.font().pointSize(), QFont.Weight.DemiBold))
        p.drawText(r.x(), r.y(), "Структура занятости за период")

        if not self._data or self._data.cap_sec <= 0:
            p.setPen(QPen(MUTED))
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

        # donut rect
        size = min(r.width(), r.height() - 30)
        cx = r.x()
        cy = r.y() + 30
        donut = QRectF(cx, cy, size, size)

        start = 90 * 16  # Qt uses 1/16 degree, 90 = вверх

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
        draw_slice(free, QColor("#e5e7eb"))

        # inner hole
        p.setBrush(QColor("#fbfbfc"))
        p.drawEllipse(donut.adjusted(size * 0.22, size * 0.22, -size * 0.22, -size * 0.22))

        # center text
        p.setPen(QPen(TEXT))
        p.setFont(QFont(self.font().family(), self.font().pointSize() + 4, QFont.Weight.Bold))
        p.drawText(donut, Qt.AlignmentFlag.AlignCenter, f"{_pct(busy, cap):.1f}%")

        # legend справа
        lx = int(donut.right() + 18)
        ly = int(donut.top() + 10)

        p.setFont(self.font())
        p.setPen(QPen(TEXT))
        p.drawText(lx, ly, f"ПД: {pd_pct:.1f}% ({_hours(pd):.1f}ч)")
        p.setPen(QPen(TEXT))
        p.drawText(lx, ly + 22, f"ГЗ: {gz_pct:.1f}% ({_hours(gz):.1f}ч)")
        p.setPen(QPen(MUTED))
        p.drawText(lx, ly + 44, f"Свободно: {free_pct:.1f}% ({_hours(free):.1f}ч)")


class UsageDetailsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.lbl_title = QLabel("Детали")
        self.lbl_title.setStyleSheet("font-weight:700; color:#0f172a; padding:0 2px;")

        self.lbl_period = QLabel("")
        self.lbl_period.setStyleSheet("color:#475569; padding:0 2px;")

        self.donut = _DonutWidget(self)
        self.bars = _BarsWidget(self)

        card = QFrame(self)
        card.setStyleSheet("QFrame{background:#ffffff; border:1px solid #e6e6e6; border-radius:12px;}")
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

    def set_data(self, data: Optional[UsageTotals]):
        if not data:
            self.lbl_title.setText("Детали")
            self.lbl_period.setText("")
        else:
            self.lbl_title.setText(data.title)
            self.lbl_period.setText(f"Период: {data.period_title}")

        self.donut.set_data(data)
        self.bars.set_data(data)
