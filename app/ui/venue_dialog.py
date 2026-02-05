from __future__ import annotations

from typing import Optional, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QDialogButtonBox,
    QSpinBox,
    QComboBox,
    QMessageBox,
)

from app.services.venue_units_manage_service import detect_units_scheme


class VenueDialog(QDialog):
    """
    Диалог площадки + настройка зон (venue_units).
    apply_units_scheme лучше вызывать снаружи после сохранения площадки.
    """

    def __init__(self, parent=None, title: str = "Площадка", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle(title)
        self._data_in = data or {}

        self.ed_name = QLineEdit(self._data_in.get("name", "") or "")
        self.ed_sport = QLineEdit(self._data_in.get("sport_type", "") or "")

        self.sp_capacity = QSpinBox()
        self.sp_capacity.setRange(0, 100000)
        cap = self._data_in.get("capacity")
        self.sp_capacity.setValue(int(cap) if cap is not None else 0)
        self.sp_capacity.setSpecialValueText("")
        self.sp_capacity.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.cmb_units = QComboBox()
        self.cmb_units.addItem("1 зона", 1)
        self.cmb_units.addItem("Делить на 2 (половины)", 2)
        self.cmb_units.addItem("Делить на 4 (четверти)", 4)

        venue_id = self._data_in.get("id")
        if venue_id:
            try:
                scheme = detect_units_scheme(int(venue_id))
                idx = self.cmb_units.findData(scheme)
                if idx >= 0:
                    self.cmb_units.setCurrentIndex(idx)
            except Exception:
                pass

        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        form.addRow("Название *:", self.ed_name)
        form.addRow("Тип спорта:", self.ed_sport)
        form.addRow("Вместимость:", self.sp_capacity)
        form.addRow("Зоны аренды:", self.cmb_units)
        form.addRow("Комментарий:", self.ed_comment)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(form)
        root.addWidget(buttons)

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
