# app/ui/badge_delegate.py
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QApplication


# Роль для хранения цвета бейджа
BADGE_BG_ROLE = Qt.ItemDataRole.UserRole + 10


class BadgeDelegate(QStyledItemDelegate):
    """
    Делегат для ячеек таблицы.
    Если у ячейки задана роль BADGE_BG_ROLE (QColor) — рисует
    цветной скруглённый бейдж с текстом поверх стандартной отрисовки.
    Остальные ячейки рисуются стандартно, но цвет текста берётся
    из ForegroundRole (обходим ограничение QSS).
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        badge_color: QColor | None = index.data(BADGE_BG_ROLE)

        if badge_color is None:
            # Стандартная ячейка — рисуем сами, чтобы QSS не перебил ForegroundRole
            self._paint_plain(painter, option, index)
            return

        # Ячейка-бейдж
        self._paint_badge(painter, option, index, badge_color)

    # ------------------------------------------------------------------
    def _paint_plain(self, painter, option, index):
        """Стандартная отрисовка с уважением ForegroundRole."""
        # Фон выделения / hover
        style = QApplication.style()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Убираем текст из opt — нарисуем сами
        opt.text = ""
        style.drawControl(style.ControlElement.CE_ItemViewItem, opt, painter)

        # Цвет текста из модели (ForegroundRole), иначе — белый
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg is not None and isinstance(fg, QColor):
            color = fg
        elif hasattr(fg, "color"):          # QBrush
            color = fg.color()
        else:
            is_selected = bool(option.state & option.state.State_Selected)
            color = QColor("white") if is_selected else QColor(255, 255, 255, 225)

        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        alignment = index.data(Qt.ItemDataRole.TextAlignmentRole)
        if alignment is None:
            alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        painter.save()
        painter.setPen(QPen(color))
        painter.drawText(option.rect.adjusted(10, 0, -10, 0), alignment, text)
        painter.restore()

    # ------------------------------------------------------------------
    def _paint_badge(self, painter, option, index, badge_color: QColor):
        """Отрисовка ячейки с цветным бейджем."""
        style = QApplication.style()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Рисуем фон строки (выделение / hover) без текста
        opt.text = ""
        style.drawControl(style.ControlElement.CE_ItemViewItem, opt, painter)

        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if not text or text == "—":
            # Нет бейджа — просто "—" белым
            painter.save()
            painter.setPen(QPen(QColor(255, 255, 255, 100)))
            painter.drawText(
                option.rect.adjusted(10, 0, -10, 0),
                Qt.AlignmentFlag.AlignCenter,
                "—",
            )
            painter.restore()
            return

        # Вычисляем размер бейджа
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()

        badge_w = text_w + 20
        badge_h = min(text_h + 8, option.rect.height() - 6)
        badge_x = option.rect.x() + (option.rect.width() - badge_w) // 2
        badge_y = option.rect.y() + (option.rect.height() - badge_h) // 2

        badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)

        # Рисуем скруглённый прямоугольник
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Фон бейджа
        painter.setBrush(QBrush(badge_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 6, 6)

        # Текст — выбираем контрастный цвет
        lum = (
            0.299 * badge_color.red()
            + 0.587 * badge_color.green()
            + 0.114 * badge_color.blue()
        )
        text_color = QColor("white") if lum < 140 else QColor("#1a1a2e")

        painter.setPen(QPen(text_color))
        f = QFont(painter.font())
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(base.height(), 32))
