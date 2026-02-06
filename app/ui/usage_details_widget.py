from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout


PD_COLOR   = QColor("#60a5fa")   # blue-400
GZ_COLOR   = QColor("#f59e0b")   # amber-500
FREE_COLOR = QColor(255, 255, 255, 22)


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


class _DonutWidget(QWidget):
    """Красивый бублик: ПД / ГЗ / Свободно с большим процентом в центре."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[UsageTotals] = None
        self.setMinimumHeight(240)

    def set_data(self, data: Optional[UsageTotals]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        margin = 16

        # ── Заголовок ──
        title_font = QFont(self.font().family(), self.font().pointSize(), QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(QColor(226, 232, 240, 160))
        title_y = margin + p.fontMetrics().ascent()
        p.drawText(margin, title_y, "Структура занятости за период")

        content_top = title_y + 14

        if not self._data or self._data.cap_sec <= 0:
            p.setFont(self.font())
            p.setPen(QColor(226, 232, 240, 120))
            p.drawText(margin, content_top + 20, "Нет данных.")
            p.end()
            return

        cap  = self._data.cap_sec
        pd   = max(0, self._data.pd_sec)
        gz   = max(0, self._data.gz_sec)
        busy = min(cap, pd + gz)
        free = max(0, cap - busy)

        pd_pct   = _pct(pd, cap)
        gz_pct   = _pct(gz, cap)
        free_pct = _pct(free, cap)
        busy_pct = _pct(busy, cap)

        # ── Размеры бублика ──
        available_h = h - content_top - margin
        donut_size = min(int(w * 0.45), available_h, 180)
        donut_size = max(donut_size, 100)

        # Центрируем бублик вертикально в доступном пространстве
        donut_x = margin
        donut_cy = content_top + available_h / 2.0
        donut_y = donut_cy - donut_size / 2.0

        outer = QRectF(donut_x, donut_y, donut_size, donut_size)

        # Толщина кольца — 30% от радиуса
        thickness_ratio = 0.30
        inner_inset = donut_size * thickness_ratio
        inner = outer.adjusted(inner_inset, inner_inset, -inner_inset, -inner_inset)

        # ── Рисуем секторы ──
        # Сначала фон (свободно) — полный круг
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 18))
        p.drawEllipse(outer)

        # Секторы ПД и ГЗ
        start_angle = 90 * 16  # начинаем сверху

        def draw_arc(val: int, color: QColor):
            nonlocal start_angle
            if val <= 0 or cap <= 0:
                return
            span = -int(360 * 16 * (val / cap))
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPie(outer, start_angle, span)
            start_angle += span

        draw_arc(pd, PD_COLOR)
        draw_arc(gz, GZ_COLOR)

        # ── Дырка бублика ──
        hole_color = QColor(11, 18, 32)  # точно цвет фона
        p.setBrush(hole_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(inner)

        # ── Тонкий разделитель между секторами и дыркой ──
        p.setPen(QPen(QColor(11, 18, 32), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(inner.adjusted(-1, -1, 1, 1))

        # ── Процент в центре ──
        center = outer.center()

        # Большой процент
        pct_font = QFont(self.font().family(), 22, QFont.Weight.Black)
        p.setFont(pct_font)
        p.setPen(QColor(255, 255, 255, 240))

        pct_text = f"{busy_pct:.0f}%"
        pct_fm = p.fontMetrics()
        pct_w = pct_fm.horizontalAdvance(pct_text)
        pct_h = pct_fm.height()
        p.drawText(QRectF(center.x() - pct_w / 2, center.y() - pct_h / 2 - 4,
                          pct_w, pct_h),
                   Qt.AlignmentFlag.AlignCenter, pct_text)

        # Подпись "занято"
        sub_font = QFont(self.font().family(), 8, QFont.Weight.Normal)
        p.setFont(sub_font)
        p.setPen(QColor(226, 232, 240, 130))
        sub_text = "занято"
        sub_fm = p.fontMetrics()
        sub_w = sub_fm.horizontalAdvance(sub_text)
        p.drawText(QRectF(center.x() - sub_w / 2, center.y() + pct_h / 2 - 8,
                          sub_w, sub_fm.height()),
                   Qt.AlignmentFlag.AlignCenter, sub_text)

        # ── Легенда (справа от бублика) ──
        legend_x = int(outer.right()) + 24
        legend_y = int(outer.top()) + 16
        legend_w = w - legend_x - margin

        if legend_w < 60:
            p.end()
            return

        items = [
            (PD_COLOR,   f"ПД: {pd_pct:.1f}% ({_hours(pd):.1f}ч)"),
            (GZ_COLOR,   f"ГЗ: {gz_pct:.1f}% ({_hours(gz):.1f}ч)"),
            (QColor(255, 255, 255, 40), f"Свободно: {free_pct:.1f}% ({_hours(free):.1f}ч)"),
        ]

        item_font = QFont(self.font().family(), self.font().pointSize(), QFont.Weight.Normal)
        p.setFont(item_font)
        ifm = p.fontMetrics()
        line_h = ifm.height() + 10

        for color, text in items:
            # Цветной маркер (кружок)
            marker_r = 6
            marker_cy = legend_y + ifm.ascent() / 2 + 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(legend_x + marker_r, marker_cy),
                          marker_r, marker_r)

            # Текст
            text_x = legend_x + marker_r * 2 + 10
            text_color = QColor(255, 255, 255, 220) if color != QColor(255, 255, 255, 40) else QColor(226, 232, 240, 140)
            p.setPen(text_color)
            p.drawText(text_x, legend_y + ifm.ascent(), text)

            legend_y += line_h

        p.end()


class _BarsWidget(QWidget):
    """Бары загрузки по сменам с улучшенным дизайном."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[UsageTotals] = None
        self._shift_titles: Tuple[str, str, str] = ("Утро", "День", "Вечер")
        self.setMinimumHeight(190)

    def set_data(self, data: Optional[UsageTotals]) -> None:
        self._data = data
        self.update()

    def set_shift_titles(self, morning: str, day: str, evening: str) -> None:
        self._shift_titles = (morning or "Утро", day or "День", evening or "Вечер")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        margin = 16
        r = self.rect().adjusted(margin, margin, -margin, -margin)

        # Заголовок
        title_font = QFont(self.font().family(), self.font().pointSize(), QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(QColor(226, 232, 240, 160))
        title_y = r.top() + p.fontMetrics().ascent()
        p.drawText(r.x(), title_y, "Загрузка по сменам (ПД / ГЗ)")

        if not self._data:
            p.setFont(self.font())
            p.setPen(QColor(226, 232, 240, 120))
            p.drawText(r.x(), title_y + 24, "Нет данных.")
            p.end()
            return

        m_title, d_title, e_title = self._shift_titles
        rows = [
            (m_title, self._data.m_cap, self._data.m_pd, self._data.m_gz),
            (d_title, self._data.d_cap, self._data.d_pd, self._data.d_gz),
            (e_title, self._data.e_cap, self._data.e_pd, self._data.e_gz),
        ]

        y = title_y + 30
        bar_h = 24
        bar_radius = 6
        row_gap = 20
        label_w = 170
        pct_w = 60
        bar_w = max(200, r.width() - label_w - pct_w - 10)

        body_font = QFont(self.font().family(), self.font().pointSize(), QFont.Weight.Normal)
        small_font = QFont(self.font().family(), max(self.font().pointSize() - 1, 8), QFont.Weight.Normal)

        for name, cap, pd_sec, gz_sec in rows:
            total = pd_sec + gz_sec
            tot_pct = _pct(total, cap)
            pd_w = 0.0 if cap <= 0 else bar_w * (pd_sec / cap)
            gz_w = 0.0 if cap <= 0 else bar_w * (gz_sec / cap)

            # Метка ПД/ГЗ часов над баром
            p.setFont(small_font)
            p.setPen(QColor(226, 232, 240, 130))
            info = f"ПД {_hours(pd_sec):.1f}ч   ГЗ {_hours(gz_sec):.1f}ч"
            p.drawText(int(r.x() + label_w), int(y - 3), info)

            # Название смены
            p.setFont(body_font)
            p.setPen(QColor(255, 255, 255, 220))
            name_y = y + bar_h / 2 + p.fontMetrics().ascent() / 2 - 2
            p.drawText(int(r.x()), int(name_y), name)

            # Фон бара
            bx = r.x() + label_w
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(QRectF(bx, y, bar_w, bar_h), bar_radius, bar_radius)

            # ПД сегмент
            if pd_w > 0:
                p.setBrush(PD_COLOR)
                # Если ПД + ГЗ заполняют весь бар — скругляем справа
                if gz_w <= 0 and pd_w >= bar_w - 1:
                    p.drawRoundedRect(QRectF(bx, y, pd_w, bar_h), bar_radius, bar_radius)
                else:
                    # Скругление только слева
                    clip_path = QPainterPath()
                    clip_path.addRoundedRect(QRectF(bx, y, bar_w, bar_h), bar_radius, bar_radius)
                    p.setClipPath(clip_path)
                    p.drawRect(QRectF(bx, y, pd_w, bar_h))
                    p.setClipping(False)

            # ГЗ сегмент
            if gz_w > 0:
                p.setBrush(GZ_COLOR)
                clip_path = QPainterPath()
                clip_path.addRoundedRect(QRectF(bx, y, bar_w, bar_h), bar_radius, bar_radius)
                p.setClipPath(clip_path)
                p.drawRect(QRectF(bx + pd_w, y, gz_w, bar_h))
                p.setClipping(False)

            # Процент справа
            p.setPen(QColor(255, 255, 255, 200))
            p.setFont(body_font)
            pct_x = bx + bar_w + 10
            p.drawText(int(pct_x), int(name_y), f"{tot_pct:.1f}%")

            y += bar_h + row_gap

        p.end()


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
