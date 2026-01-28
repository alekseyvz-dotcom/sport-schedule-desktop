from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
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
        venue_units: Optional[List[Dict]] = None,  # [{id, name}]
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._venue_units = venue_units or []

        self.lbl_info = QLabel(
            f"Площадка: <b>{venue_name}</b><br>"
            f"Время: <b>{starts_at:%d.%m.%Y %H:%M}</b> – <b>{ends_at:%H:%M}</b>"
        )
        self.lbl_info.setWordWrap(True)

        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem("ПД", "PD")
        self.cmb_kind.addItem("ГЗ", "GZ")

        self.cmb_tenant = QComboBox()
        for t in tenants:
            self.cmb_tenant.addItem(t["name"], t["id"])

        # NEW: выбор зоны
        self.cmb_unit = QComboBox()
        if self._venue_units:
            for u in self._venue_units:
                self.cmb_unit.addItem(u["name"], u["id"])
        else:
            self.cmb_unit.addItem("—", None)
            self.cmb_unit.setEnabled(False)

        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Например: Тренировка / Секция / Аренда")

        form = QFormLayout()
        form.addRow("Тип занятости:", self.cmb_kind)
        form.addRow("Контрагент:", self.cmb_tenant)
        if self._venue_units:
            form.addRow("Зона:", self.cmb_unit)
        form.addRow("Название *:", self.ed_title)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)

        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(self.lbl_info)
        root.addLayout(form)
        root.addWidget(self.buttons)

    def _on_accept(self):
        title = self.ed_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Создать бронирование", "Введите название.")
            self.ed_title.setFocus()
            return
        self.accept()

    def values(self) -> Dict:
        unit_id = self.cmb_unit.currentData()
        return {
            "kind": self.cmb_kind.currentData(),
            "tenant_id": int(self.cmb_tenant.currentData()),
            "venue_unit_id": (int(unit_id) if unit_id is not None else None),
            "title": self.ed_title.text().strip(),
        }
