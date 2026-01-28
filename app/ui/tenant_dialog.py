from __future__ import annotations

from typing import Optional, Dict
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QTextEdit,
    QDateEdit,
    QCheckBox,
    QComboBox,
)


def _pydate_to_qdate(d: Optional[date]) -> QDate:
    if not d:
        return QDate()
    return QDate(d.year, d.month, d.day)


def _qdate_to_pydate(qd: QDate) -> Optional[date]:
    if not qd.isValid():
        return None
    return date(qd.year(), qd.month(), qd.day())


class TenantDialog(QDialog):
    def __init__(self, parent=None, title: str = "Контрагент", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._data_in = data or {}

        # базовые
        self.ed_name = QLineEdit(self._data_in.get("name", ""))
        self.ed_inn = QLineEdit(self._data_in.get("inn", "") or "")
        self.ed_phone = QLineEdit(self._data_in.get("phone", "") or "")
        self.ed_email = QLineEdit(self._data_in.get("email", "") or "")
        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        # доп поля
        self.ed_contact_name = QLineEdit(self._data_in.get("contact_name", "") or "")
        self.ed_obligation_kind = QLineEdit(self._data_in.get("obligation_kind", "") or "")
        self.ed_contract_no = QLineEdit(self._data_in.get("contract_no", "") or "")

        self.dt_contract_date = QDateEdit()
        self.dt_contract_date.setCalendarPopup(True)
        self.dt_contract_date.setSpecialValueText("—")
        self.dt_contract_date.setDate(_pydate_to_qdate(self._data_in.get("contract_date")))
        self.dt_contract_date.setMinimumDate(QDate(1900, 1, 1))

        self.dt_valid_from = QDateEdit()
        self.dt_valid_from.setCalendarPopup(True)
        self.dt_valid_from.setSpecialValueText("—")
        self.dt_valid_from.setDate(_pydate_to_qdate(self._data_in.get("contract_valid_from")))
        self.dt_valid_from.setMinimumDate(QDate(1900, 1, 1))

        self.dt_valid_to = QDateEdit()
        self.dt_valid_to.setCalendarPopup(True)
        self.dt_valid_to.setSpecialValueText("—")
        self.dt_valid_to.setDate(_pydate_to_qdate(self._data_in.get("contract_valid_to")))
        self.dt_valid_to.setMinimumDate(QDate(1900, 1, 1))

        self.ed_docs_delivery = QLineEdit(self._data_in.get("docs_delivery_method", "") or "")

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("active", "active")
        self.cmb_status.addItem("paused", "paused")
        self.cmb_status.addItem("closed", "closed")
        cur_status = (self._data_in.get("status") or "active").strip()
        idx = self.cmb_status.findData(cur_status)
        self.cmb_status.setCurrentIndex(idx if idx >= 0 else 0)

        self.cb_signed = QCheckBox("Подписанный договор")
        self.cb_signed.setChecked(bool(self._data_in.get("contract_signed") or False))

        self.cb_attached_1c = QCheckBox("Прикреплен в 1С")
        self.cb_attached_1c.setChecked(bool(self._data_in.get("attached_in_1c") or False))

        self.cb_has_ds = QCheckBox("ДС")
        self.cb_has_ds.setChecked(bool(self._data_in.get("has_ds") or False))

        self.ed_notes = QTextEdit(self._data_in.get("notes", "") or "")

        form = QFormLayout()
        form.addRow("Название *:", self.ed_name)
        form.addRow("ИНН:", self.ed_inn)
        form.addRow("Телефон:", self.ed_phone)
        form.addRow("Email:", self.ed_email)
        form.addRow("Комментарий:", self.ed_comment)

        form.addRow("Контакт:", self.ed_contact_name)
        form.addRow("Вид обязательства:", self.ed_obligation_kind)
        form.addRow("№ договора:", self.ed_contract_no)
        form.addRow("Дата договора:", self.dt_contract_date)
        form.addRow("Срок действия с:", self.dt_valid_from)
        form.addRow("Срок действия по:", self.dt_valid_to)
        form.addRow("Способ передачи документов:", self.ed_docs_delivery)
        form.addRow("Статус:", self.cmb_status)
        form.addRow("", self.cb_signed)
        form.addRow("", self.cb_attached_1c)
        form.addRow("", self.cb_has_ds)
        form.addRow("Примечания:", self.ed_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def values(self) -> Dict:
        return {
            "name": self.ed_name.text().strip(),
            "inn": self.ed_inn.text().strip(),
            "phone": self.ed_phone.text().strip(),
            "email": self.ed_email.text().strip(),
            "comment": self.ed_comment.toPlainText().strip(),

            "contact_name": self.ed_contact_name.text().strip(),
            "obligation_kind": self.ed_obligation_kind.text().strip(),
            "contract_no": self.ed_contract_no.text().strip(),
            "contract_date": _qdate_to_pydate(self.dt_contract_date.date()),
            "contract_valid_from": _qdate_to_pydate(self.dt_valid_from.date()),
            "contract_valid_to": _qdate_to_pydate(self.dt_valid_to.date()),
            "docs_delivery_method": self.ed_docs_delivery.text().strip(),
            "status": self.cmb_status.currentData(),
            "contract_signed": self.cb_signed.isChecked(),
            "attached_in_1c": self.cb_attached_1c.isChecked(),
            "has_ds": self.cb_has_ds.isChecked(),
            "notes": self.ed_notes.toPlainText().strip(),
        }
