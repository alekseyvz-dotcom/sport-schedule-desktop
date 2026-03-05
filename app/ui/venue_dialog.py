from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QDialogButtonBox,
    QSpinBox,
    QComboBox,
    QMessageBox,
    QGroupBox,
    QLabel,
    QGridLayout,
)

from app.services.venue_units_manage_service import detect_units_scheme
from app.services.venue_prices_service import get_venue_prices, VenuePrices


class _PriceEdit(QLineEdit):
    """Поле ввода цены с placeholder и валидацией."""

    def __init__(self, value: Optional[Decimal] = None, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("—")
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setFixedWidth(120)
        if value is not None:
            self.setText(str(int(value)) if value == int(value) else str(value))

    def decimal_value(self) -> Optional[Decimal]:
        text = self.text().strip().replace(",", ".").replace(" ", "")
        if not text:
            return None
        try:
            v = Decimal(text)
            if v < 0:
                return None
            return v
        except InvalidOperation:
            return None


class VenueDialog(QDialog):
    """
    Диалог площадки + настройка зон (venue_units) + прайс-лист.
    """

    def __init__(self, parent=None, title: str = "Площадка", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self._data_in = data or {}

        # ── Основные поля ──
        self.ed_name = QLineEdit(self._data_in.get("name", "") or "")
        self.ed_sport = QLineEdit(self._data_in.get("sport_type", "") or "")

        self.sp_capacity = QSpinBox()
        self.sp_capacity.setRange(0, 100000)
        cap = self._data_in.get("capacity")
        self.sp_capacity.setValue(int(cap) if cap is not None else 0)
        self.sp_capacity.setSpecialValueText("")
        self.sp_capacity.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.cmb_units = QComboBox()
        self.cmb_units.addItem("1 зона", 1)
        self.cmb_units.addItem("Делить на 2 (половины)", 2)
        self.cmb_units.addItem("Делить на 4 (четверти)", 4)

        venue_id = self._data_in.get("id")
        self._venue_id = venue_id

        if venue_id:
            try:
                scheme = detect_units_scheme(int(venue_id))
                idx = self.cmb_units.findData(scheme)
                if idx >= 0:
                    self.cmb_units.setCurrentIndex(idx)
            except Exception:
                pass

        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")
        self.ed_comment.setMaximumHeight(80)

        # ── Прайс-лист ──
        prices = VenuePrices(venue_id=venue_id or 0)
        if venue_id:
            try:
                prices = get_venue_prices(int(venue_id))
            except Exception:
                pass

        self.price_q_60 = _PriceEdit(prices.price_q_60)
        self.price_q_90 = _PriceEdit(prices.price_q_90)
        self.price_h_60 = _PriceEdit(prices.price_h_60)
        self.price_h_90 = _PriceEdit(prices.price_h_90)
        self.price_f_60 = _PriceEdit(prices.price_f_60)
        self.price_f_90 = _PriceEdit(prices.price_f_90)

        price_group = QGroupBox("Прайс-лист (₽)")
        price_grid = QGridLayout(price_group)
        price_grid.setContentsMargins(8, 12, 8, 8)
        price_grid.setHorizontalSpacing(12)
        price_grid.setVerticalSpacing(8)

        # Заголовки
        price_grid.addWidget(QLabel(""), 0, 0)
        lbl_60 = QLabel("60 мин")
        lbl_60.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_90 = QLabel("90 мин")
        lbl_90.setAlignment(Qt.AlignmentFlag.AlignCenter)
        price_grid.addWidget(lbl_60, 0, 1)
        price_grid.addWidget(lbl_90, 0, 2)

        # 1/4 поля
        self.lbl_q = QLabel("1/4 поля:")
        self.lbl_q.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        price_grid.addWidget(self.lbl_q, 1, 0)
        price_grid.addWidget(self.price_q_60, 1, 1)
        price_grid.addWidget(self.price_q_90, 1, 2)

        # 1/2 поля
        self.lbl_h = QLabel("1/2 поля:")
        self.lbl_h.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        price_grid.addWidget(self.lbl_h, 2, 0)
        price_grid.addWidget(self.price_h_60, 2, 1)
        price_grid.addWidget(self.price_h_90, 2, 2)

        # Целое поле
        lbl_f = QLabel("Целое поле:")
        lbl_f.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        price_grid.addWidget(lbl_f, 3, 0)
        price_grid.addWidget(self.price_f_60, 3, 1)
        price_grid.addWidget(self.price_f_90, 3, 2)

        # Связываем видимость строк прайса с выбором зон
        self.cmb_units.currentIndexChanged.connect(self._update_price_visibility)
        self._update_price_visibility()

        # ── Основная форма ──
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        form.addRow("Название *:", self.ed_name)
        form.addRow("Тип спорта:", self.ed_sport)
        form.addRow("Вместимость:", self.sp_capacity)
        form.addRow("Зоны аренды:", self.cmb_units)
        form.addRow("Комментарий:", self.ed_comment)

        # ── Кнопки ──
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        # ── Layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(form)
        root.addWidget(price_group)
        root.addWidget(buttons)

    def _update_price_visibility(self):
        """Показывает/скрывает строки прайса в зависимости от схемы зон."""
        scheme = int(self.cmb_units.currentData() or 1)

        # 1/4 — только для схемы 4
        show_q = (scheme == 4)
        self.lbl_q.setVisible(show_q)
        self.price_q_60.setVisible(show_q)
        self.price_q_90.setVisible(show_q)

        # 1/2 — для схемы 2 и 4
        show_h = (scheme in (2, 4))
        self.lbl_h.setVisible(show_h)
        self.price_h_60.setVisible(show_h)
        self.price_h_90.setVisible(show_h)

        # Целое — всегда видно

    def _on_accept(self):
        if not (self.ed_name.text() or "").strip():
            QMessageBox.warning(self, "Площадка", "Введите название.")
            self.ed_name.setFocus()
            return
        self.accept()

    def values(self) -> Dict:
        cap = int(self.sp_capacity.value())
        return {
            "name": (self.ed_name.text() or "").strip(),
            "sport_type": (self.ed_sport.text() or "").strip(),
            "capacity": None if cap == 0 else cap,
            "units_scheme": int(self.cmb_units.currentData()),
            "comment": (self.ed_comment.toPlainText() or "").strip(),
        }

    def price_values(self) -> VenuePrices:
        """Возвращает объект цен для сохранения."""
        return VenuePrices(
            venue_id=self._venue_id or 0,
            price_q_60=self.price_q_60.decimal_value(),
            price_q_90=self.price_q_90.decimal_value(),
            price_h_60=self.price_h_60.decimal_value(),
            price_h_90=self.price_h_90.decimal_value(),
            price_f_60=self.price_f_60.decimal_value(),
            price_f_90=self.price_f_90.decimal_value(),
        )
