# app/ui/booking_dialog.py
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional, Set

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QListView,
    QAbstractItemView,
)


def _make_scrollable_combo(cmb: QComboBox, *, max_visible: int = 14) -> None:
    view = QListView()
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    cmb.setView(view)
    cmb.setMaxVisibleItems(int(max_visible))


class BookingDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str = "Создать бронирование",
        starts_at: datetime,
        ends_at: datetime,
        venue_name: str,
        tenants: List[Dict],            # [{id, name}]
        gz_groups: List[Dict],          # [{id, name}]
        venue_units: Optional[List[Dict]] = None,  # [{id, name}]
        initial: Optional[Dict] = None,            # {kind, tenant_id|gz_group_id, venue_unit_id, title}
        selection_title: Optional[str] = None,
        selection_lines: Optional[List[str]] = None,
        allowed_kinds: Optional[Set[str]] = None,  # {"PD","GZ"}; если None -> оба
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._venue_units = venue_units or []
        self._tenants = tenants or []
        self._gz_groups = gz_groups or []
        initial = initial or {}

        self._allowed_kinds = {k.upper() for k in (allowed_kinds or {"PD", "GZ"})}
        if not self._allowed_kinds:
            self._allowed_kinds = {"PD", "GZ"}

        self.lbl_info = QLabel(
            f"Площадка: <b>{venue_name}</b><br>"
            f"Время: <b>{starts_at:%d.%m.%Y %H:%M}</b> – <b>{ends_at:%H:%M}</b>"
        )
        self.lbl_info.setWordWrap(True)

        self.lbl_selection = QLabel("")
        self.lbl_selection.setWordWrap(True)
        self.lbl_selection.setVisible(False)
        if selection_title or selection_lines:
            lines = selection_lines or []
            text = f"<b>{selection_title or ''}</b>"
            if lines:
                text += "<br>" + "<br>".join(f"• {s}" for s in lines)
            self.lbl_selection.setText(text)
            self.lbl_selection.setVisible(True)

        self.cmb_kind = QComboBox()
        if "PD" in self._allowed_kinds:
            self.cmb_kind.addItem("ПД (контрагент)", "PD")
        if "GZ" in self._allowed_kinds:
            self.cmb_kind.addItem("ГЗ (гос. задание)", "GZ")
        self.cmb_kind.setEnabled(self.cmb_kind.count() > 1)

        self.cmb_subject = QComboBox()
        _make_scrollable_combo(self.cmb_subject, max_visible=14)

        self.lbl_subject = QLabel("Контрагент:")

        self.cmb_unit = QComboBox()
        _make_scrollable_combo(self.cmb_unit, max_visible=12)
        if self._venue_units:
            for u in self._venue_units:
                self.cmb_unit.addItem(u["name"], u["id"])
        else:
            self.cmb_unit.addItem("—", None)
            self.cmb_unit.setEnabled(False)

        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Необязательно. Например: Тренировка / Секция / Аренда")

        self.cmb_kind.currentIndexChanged.connect(self._rebuild_subjects)

        # --- initial ---
        k = (initial.get("kind") or "PD").upper()
        i = self.cmb_kind.findData(k)
        if i >= 0:
            self.cmb_kind.setCurrentIndex(i)
        else:
            self.cmb_kind.setCurrentIndex(0)

        self._rebuild_subjects()

        kind_now = (self.cmb_kind.currentData() or "PD").upper()
        if kind_now == "GZ":
            gid = initial.get("gz_group_id")
            if gid is not None:
                i = self.cmb_subject.findData(int(gid))
                if i >= 0:
                    self.cmb_subject.setCurrentIndex(i)
        else:
            tid = initial.get("tenant_id")
            if tid is not None:
                i = self.cmb_subject.findData(int(tid))
                if i >= 0:
                    self.cmb_subject.setCurrentIndex(i)

        unit_id = initial.get("venue_unit_id")
        if self._venue_units and unit_id is not None:
            i = self.cmb_unit.findData(int(unit_id))
            if i >= 0:
                self.cmb_unit.setCurrentIndex(i)

        self.ed_title.setText((initial.get("title") or "").strip())
        # --- end initial ---

        form = QFormLayout()
        form.addRow("Тип занятости:", self.cmb_kind)
        form.addRow(self.lbl_subject, self.cmb_subject)
        if self._venue_units:
            form.addRow("Зона:", self.cmb_unit)
        form.addRow("Название:", self.ed_title)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(self.lbl_info)
        root.addWidget(self.lbl_selection)
        root.addLayout(form)
        root.addWidget(self.buttons)

    def _rebuild_subjects(self):
        kind = (self.cmb_kind.currentData() or "PD").upper()

        self.cmb_subject.blockSignals(True)
        self.cmb_subject.clear()

        if kind == "GZ":
            self.lbl_subject.setText("Гос. задание (группа):")
            for g in self._gz_groups:
                self.cmb_subject.addItem(g["name"], g["id"])
        else:
            self.lbl_subject.setText("Контрагент:")
            for t in self._tenants:
                self.cmb_subject.addItem(t["name"], t["id"])

        self.cmb_subject.blockSignals(False)

    def values(self) -> Dict:
        unit_id = self.cmb_unit.currentData()
        kind = (self.cmb_kind.currentData() or "PD").upper()
        subject_id = self.cmb_subject.currentData()

        out = {
            "kind": kind,
            "venue_unit_id": (int(unit_id) if unit_id is not None else None),
            "title": self.ed_title.text().strip(),
        }

        if kind == "GZ":
            out["gz_group_id"] = int(subject_id) if subject_id is not None else None
            out["tenant_id"] = None
        else:
            out["tenant_id"] = int(subject_id) if subject_id is not None else None
            out["gz_group_id"] = None

        return out
