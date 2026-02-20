# app/ui/period_edit_dialog.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QMessageBox, QDateEdit, QCheckBox
)


@dataclass(frozen=True)
class PeriodValues:
    date_from: date
    date_to: date
    reason: str
    is_active: bool


class PeriodEditDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        reason: str = "",
        show_active: bool = True,
        is_active: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle(title)

        self.dt_from = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("dd.MM.yyyy")

        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("dd.MM.yyyy")

        today = date.today()
        self.dt_from.setDate(self._to_qdate(date_from or today))
        self.dt_to.setDate(self._to_qdate(date_to or (date_from or today)))

        self.ed_reason = QTextEdit(reason or "")

        self.cb_active = QCheckBox("Активно")
        self.cb_active.setChecked(bool(is_active))
        self.cb_active.setVisible(bool(show_active))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("С *:", self.dt_from)
        form.addRow("По *:", self.dt_to)
        form.addRow("Причина:", self.ed_reason)
        form.addRow("", self.cb_active)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(form)
        root.addWidget(buttons)

    def _to_qdate(self, d: date) -> QDate:
        return QDate(d.year, d.month, d.day)

    def _on_accept(self):
        df = self.dt_from.date()
        dt = self.dt_to.date()
        if dt < df:
            QMessageBox.warning(self, "Период", "Дата 'По' должна быть не раньше даты 'С'.")
            return
        self.accept()

    def values(self) -> PeriodValues:
        df = self.dt_from.date()
        dt = self.dt_to.date()
        return PeriodValues(
            date_from=date(df.year(), df.month(), df.day()),
            date_to=date(dt.year(), dt.month(), dt.day()),
            reason=(self.ed_reason.toPlainText() or "").strip(),
            is_active=bool(self.cb_active.isChecked()),
        )
