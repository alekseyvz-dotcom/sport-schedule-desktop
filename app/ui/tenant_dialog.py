from __future__ import annotations

from typing import Optional, Dict
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QTextEdit,
    QDateEdit,
    QCheckBox,
    QComboBox,
    QMessageBox,
    QLabel,
    QGroupBox,
)

from app.ui.tenant_rules_widget import TenantRulesWidget


def _pydate_to_qdate(d: Optional[date]) -> QDate:
    if not d:
        return QDate()  # invalid
    return QDate(d.year, d.month, d.day)


def _qdate_to_pydate(qd: QDate) -> Optional[date]:
    if not qd.isValid():
        return None
    return date(qd.year(), qd.month(), qd.day())


_DIALOG_QSS = """
QDialog {
    background: #fbfbfc;
}
QLineEdit, QTextEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #7fb3ff;
}
QTextEdit {
    min-height: 84px;
}
QGroupBox {
    border: 1px solid #e6e6e6;
    border-radius: 12px;
    margin-top: 10px;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #111111;
    font-weight: 700;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
    min-height: 34px;
}
QPushButton:hover {
    border: 1px solid #cfd6df;
    background: #f6f7f9;
}
QPushButton:pressed {
    background: #eef1f5;
}
"""


class TenantDialog(QDialog):
    """
    Карточка контрагента (тенант).
    Две колонки + блок правил расписания.
    """

    def __init__(self, parent=None, title: str = "Контрагент", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_QSS)

        self._data_in = data or {}
        self._tenant_id: Optional[int] = self._data_in.get("id")

        # размер чуть больше, чтобы влезли правила
        self.resize(1060, 650)

        # ---- widgets
        self.ed_name = QLineEdit(self._data_in.get("name", "") or "")
        self.ed_inn = QLineEdit(self._data_in.get("inn", "") or "")
        self.ed_phone = QLineEdit(self._data_in.get("phone", "") or "")
        self.ed_email = QLineEdit(self._data_in.get("email", "") or "")

        self.ed_contact_name = QLineEdit(self._data_in.get("contact_name", "") or "")
        self.ed_obligation_kind = QLineEdit(self._data_in.get("obligation_kind", "") or "")
        self.ed_contract_no = QLineEdit(self._data_in.get("contract_no", "") or "")
        self.ed_docs_delivery = QLineEdit(self._data_in.get("docs_delivery_method", "") or "")

        self.dt_contract_date = self._mk_date(self._data_in.get("contract_date"))
        self.dt_valid_from = self._mk_date(self._data_in.get("contract_valid_from"))
        self.dt_valid_to = self._mk_date(self._data_in.get("contract_valid_to"))

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

        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")
        self.ed_notes = QTextEdit(self._data_in.get("notes", "") or "")

        # ---- group: Основное
        gb_main = QGroupBox("Основное")
        fm_main = QFormLayout(gb_main)
        fm_main.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fm_main.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        fm_main.setHorizontalSpacing(12)
        fm_main.setVerticalSpacing(10)
        fm_main.addRow("Название *:", self.ed_name)
        fm_main.addRow("ИНН:", self.ed_inn)
        fm_main.addRow("Телефон:", self.ed_phone)
        fm_main.addRow("Email:", self.ed_email)

        # ---- group: Договор / реквизиты
        gb_contract = QGroupBox("Договор")
        grid = QGridLayout(gb_contract)
        grid.setContentsMargins(12, 16, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel("№ договора:"), 0, 0)
        grid.addWidget(self.ed_contract_no, 0, 1)
        grid.addWidget(QLabel("Дата договора:"), 0, 2)
        grid.addWidget(self.dt_contract_date, 0, 3)

        grid.addWidget(QLabel("Срок с:"), 1, 0)
        grid.addWidget(self.dt_valid_from, 1, 1)
        grid.addWidget(QLabel("Срок по:"), 1, 2)
        grid.addWidget(self.dt_valid_to, 1, 3)

        grid.addWidget(QLabel("Контакт:"), 2, 0)
        grid.addWidget(self.ed_contact_name, 2, 1)
        grid.addWidget(QLabel("Вид обязательства:"), 2, 2)
        grid.addWidget(self.ed_obligation_kind, 2, 3)

        grid.addWidget(QLabel("Способ передачи документов:"), 3, 0)
        grid.addWidget(self.ed_docs_delivery, 3, 1, 1, 3)

        grid.addWidget(QLabel("Статус:"), 4, 0)
        grid.addWidget(self.cmb_status, 4, 1)
        grid.addWidget(self.cb_signed, 4, 2)
        grid.addWidget(self.cb_attached_1c, 4, 3)

        grid.addWidget(self.cb_has_ds, 5, 2)

        # ---- group: Комментарии / примечания
        gb_notes = QGroupBox("Комментарии")
        fm_notes = QFormLayout(gb_notes)
        fm_notes.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        fm_notes.setHorizontalSpacing(12)
        fm_notes.setVerticalSpacing(10)
        fm_notes.addRow("Комментарий:", self.ed_comment)
        fm_notes.addRow("Примечания:", self.ed_notes)

        # ---- group: Правила расписания
        gb_rules = QGroupBox("Правила расписания")
        rules_layout = QVBoxLayout(gb_rules)
        rules_layout.setContentsMargins(12, 16, 12, 12)

        contract_from = _qdate_to_pydate(self.dt_valid_from.date())
        contract_to = _qdate_to_pydate(self.dt_valid_to.date())

        self.rules_widget = TenantRulesWidget(
            self,
            tenant_id=self._tenant_id,
            contract_from=contract_from,
            contract_to=contract_to,
        )
        rules_layout.addWidget(self.rules_widget)

        # ---- layout: two columns (left/right)
        cols = QHBoxLayout()
        cols.setContentsMargins(12, 12, 12, 8)
        cols.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addWidget(gb_main)
        left_col.addWidget(gb_notes)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(gb_contract)
        right_col.addWidget(gb_rules, 1)

        cols.addLayout(left_col, 1)
        cols.addLayout(right_col, 1)

        # ---- buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)

        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(cols)
        root.addWidget(buttons)

    def _mk_date(self, d: Optional[date]) -> QDateEdit:
        w = QDateEdit()
        w.setCalendarPopup(True)
        w.setDisplayFormat("dd.MM.yyyy")
        w.setSpecialValueText("—")
        w.setMinimumDate(QDate(1900, 1, 1))
        w.setDate(_pydate_to_qdate(d))
        return w

    def _on_accept(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Контрагент", "Введите название.")
            self.ed_name.setFocus()
            return

        d_from = _qdate_to_pydate(self.dt_valid_from.date())
        d_to = _qdate_to_pydate(self.dt_valid_to.date())
        if d_from and d_to and d_to < d_from:
            QMessageBox.warning(self, "Контрагент", "Срок действия: дата 'по' не может быть раньше даты 'с'.")
            return

        self.accept()

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

    def rules_payload(self) -> list[dict]:
        """
        Правила, которые пользователь добавил/изменил/отключил в карточке.
        Сохранять их в БД нужно в TenantsPage после dlg.exec().
        """
        return self.rules_widget.rules_payload()
