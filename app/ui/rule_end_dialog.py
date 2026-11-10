# app/ui/rule_end_dialog.py
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.services.tenant_rules_service import count_future_rule_bookings
from app.ui.fit_screen import fit_dialog_to_screen


class RuleEndDialog(QDialog):
    """
    Завершение правила: пользователь выбирает дату, с которой правило
    перестаёт действовать. Все брони по правилу с этой даты отменяются,
    прошлые остаются.
    """

    def __init__(
        self,
        parent,
        *,
        rule_id: int,
        rule_title: str,
        valid_from: date,
        valid_to: date,
        user_id: int,
        role_code: str,
    ):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Завершить правило")
        self.setModal(True)

        self._rule_id = int(rule_id)
        self._valid_from = valid_from
        self._valid_to = valid_to

        lbl_rule = QLabel(rule_title or "Правило")
        lbl_rule.setObjectName("sectionTitle")
        lbl_rule.setWordWrap(True)

        self.dt_end = QDateEdit()
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat("dd.MM.yyyy")
        self.dt_end.setMinimumDate(QDate(valid_from.year, valid_from.month, valid_from.day))
        self.dt_end.setMaximumDate(QDate(valid_to.year, valid_to.month, valid_to.day))
        today = date.today()
        start = max(today, valid_from)
        if start > valid_to:
            start = valid_to
        self.dt_end.setDate(QDate(start.year, start.month, start.day))
        self.dt_end.dateChanged.connect(self._refresh_info)

        self.ed_reason = QLineEdit()
        self.ed_reason.setPlaceholderText("Например: клуб прекратил занятия")

        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setObjectName("detailsText")

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addRow("Завершить с:", self.dt_end)
        form.addRow("Причина:", self.ed_reason)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Завершить")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        root.addWidget(lbl_rule)
        root.addWidget(QLabel(f"Действует: {valid_from:%d.%m.%Y} — {valid_to:%d.%m.%Y}"))
        root.addLayout(form)
        root.addWidget(self.lbl_info)
        root.addStretch(1)
        root.addWidget(buttons)

        self._refresh_info()
        fit_dialog_to_screen(self, width=480, height=280)

    def end_date(self) -> date:
        d = self.dt_end.date()
        return date(d.year(), d.month(), d.day())

    def reason(self) -> str:
        return self.ed_reason.text().strip()

    def _refresh_info(self, *_):
        d = self.end_date()
        try:
            n = count_future_rule_bookings(rule_id=self._rule_id, from_day=d)
        except Exception as e:
            self.lbl_info.setText(f"Не удалось посчитать брони: {e}")
            return
        if n == 0:
            self.lbl_info.setText(
                "С этой даты правило перестанет действовать. Будущих броней по нему нет."
            )
        else:
            self.lbl_info.setText(
                f"С этой даты правило перестанет действовать. "
                f"Будет отменено броней: {n}. Прошлые брони сохранятся."
            )

    def _on_accept(self):
        d = self.end_date()
        if d < self._valid_from:
            QMessageBox.warning(self, "Завершить правило", "Дата раньше начала правила.")
            return
        try:
            n = count_future_rule_bookings(rule_id=self._rule_id, from_day=d)
        except Exception as e:
            QMessageBox.critical(self, "Завершить правило", f"Ошибка: {e}")
            return
        msg = (
            f"Завершить правило с {d:%d.%m.%Y}?\n\n"
            f"Будет отменено броней: {n}.\n"
            "Прошлые брони останутся без изменений."
        )
        if QMessageBox.question(
            self, "Подтверждение", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.accept()
