from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QLabel
)

class BookingDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str = "Создать бронирование",
        starts_at: datetime,
        ends_at: datetime,
        tenants: List[Dict],          # [{id, name}]
        venue_name: str,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self.lbl_info = QLabel(f"Площадка: <b>{venue_name}</b><br>"
                               f"Время: <b>{starts_at:%d.%m.%Y %H:%M}</b> – <b>{ends_at:%H:%M}</b>")
        self.lbl_info.setWordWrap(True)

        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem("ПД", "PD")
        self.cmb_kind.addItem("ГЗ", "GZ")

        self.cmb_tenant = QComboBox()
        for t in tenants:
            self.cmb_tenant.addItem(t["name"], t["id"])

        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Например: Тренировка / Секция / Аренда")

        form = QFormLayout()
        form.addRow("Тип занятости:", self.cmb_kind)
        form.addRow("Арендатор:", self.cmb_tenant)
        form.addRow("Название *:", self.ed_title)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(self.lbl_info)
        root.addLayout(form)
        root.addWidget(buttons)

    def values(self) -> Dict:
        return {
            "kind": self.cmb_kind.currentData(),
            "tenant_id": int(self.cmb_tenant.currentData()),
            "title": self.ed_title.text().strip(),
        }
