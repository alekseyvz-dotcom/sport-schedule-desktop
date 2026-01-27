from __future__ import annotations

from typing import Optional, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox, QSpinBox
)

class VenueDialog(QDialog):
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

        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        form = QFormLayout()
        form.addRow("Название *:", self.ed_name)
        form.addRow("Тип спорта:", self.ed_sport)
        form.addRow("Вместимость:", self.sp_capacity)
        form.addRow("Комментарий:", self.ed_comment)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def values(self) -> Dict:
        cap = self.sp_capacity.value()
        return {
            "name": self.ed_name.text().strip(),
            "sport_type": self.ed_sport.text().strip(),
            "capacity": None if cap == 0 else cap,
            "comment": self.ed_comment.toPlainText().strip(),
        }
