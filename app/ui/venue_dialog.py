from __future__ import annotations

from typing import Optional, Dict

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
    Сами изменения в БД (apply_units_scheme) лучше вызывать снаружи,
    после успешного сохранения площадки, когда у нас точно есть venue_id.
    """

    def __init__(self, parent=None, title: str = "Площадка", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._data_in = data or {}

        self.ed_name = QLineEdit(self._data_in.get("name", ""))
        self.ed_sport = QLineEdit(self._data_in.get("sport_type", "") or "")

        self.sp_capacity = QSpinBox()
        self.sp_capacity.setRange(0, 100000)
        cap = self._data_in.get("capacity")
        self.sp_capacity.setValue(int(cap) if cap is not None else 0)
        self.sp_capacity.setSpecialValueText("")

        # NEW: схема зон
        self.cmb_units = QComboBox()
        self.cmb_units.addItem("Не делить (1 зона)", 0)
        self.cmb_units.addItem("Делить на 2 (половины)", 2)
        self.cmb_units.addItem("Делить на 4 (четверти)", 4)

        # если редактирование и venue_id известен — попытаемся определить схему по БД
        venue_id = self._data_in.get("id")
        if venue_id:
            try:
                scheme = detect_units_scheme(int(venue_id))
                idx = self.cmb_units.findData(scheme)
                if idx >= 0:
                    self.cmb_units.setCurrentIndex(idx)
            except Exception:
                # не критично, просто оставим значение по умолчанию
                pass
        else:
            # для новых площадок можно умно подставить по sport_type/названию
            pass

        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        form = QFormLayout()
        form.addRow("Название *:", self.ed_name)
        form.addRow("Тип спорта:", self.ed_sport)
        form.addRow("Вместимость:", self.sp_capacity)
        form.addRow("Зоны аренды:", self.cmb_units)
        form.addRow("Комментарий:", self.ed_comment)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def _on_accept(self):
        if not self.ed_name.text().strip():
            QMessageBox.warning(self, "Площадка", "Введите название.")
            self.ed_name.setFocus()
            return
        self.accept()

    def values(self) -> Dict:
        cap = self.sp_capacity.value()
        return {
            "name": self.ed_name.text().strip(),
            "sport_type": self.ed_sport.text().strip(),
            "capacity": None if cap == 0 else cap,
            "units_scheme": int(self.cmb_units.currentData()),  # NEW
            "comment": self.ed_comment.toPlainText().strip(),
        }
