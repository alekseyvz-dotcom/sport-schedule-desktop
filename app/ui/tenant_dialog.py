from __future__ import annotations

from typing import Optional, Dict, List
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
    QComboBox,
    QMessageBox,
    QLabel,
    QGroupBox,
    QWidget,
)

from app.ui.tenant_rules_widget import TenantRulesWidget


def _pydate_to_qdate(d: Optional[date]) -> QDate:
    if not d:
        return QDate()
    return QDate(d.year, d.month, d.day)


def _qdate_to_pydate(qd: QDate) -> Optional[date]:
    if not qd.isValid():
        return None
    return date(qd.year(), qd.month(), qd.day())


_DIALOG_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QTextEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #7fb3ff;
}
QTextEdit { min-height: 84px; }
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
QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
QPushButton:pressed { background: #eef1f5; }
"""


_OBLIGATION_OPTIONS = [
    "орг группа 60 минут",
    "орг группа 90 минут",
    "мероприятия",
]

_DELIVERY_OPTIONS = [
    "ЭДО",
    "физически",
]


class TenantDialog(QDialog):
    """
    Карточка контрагента (тенант).
    """

    def __init__(
        self,
        parent=None,
        title: str = "Контрагент",
        data: Optional[Dict] = None,
        *,
        is_admin: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_QSS)

        self._is_admin = bool(is_admin)

        self._data_in = data or {}
        self._tenant_id: Optional[int] = self._data_in.get("id")

        self._tenant_kind_in = (self._data_in.get("tenant_kind") or "legal").strip()
        self._rent_kind_in = (self._data_in.get("rent_kind") or "long_term").strip()

        self.resize(1060, 650)

        # ---- widgets (общие)
        self.ed_name = QLineEdit(self._data_in.get("name", "") or "")
        self.ed_phone = QLineEdit(self._data_in.get("phone", "") or "")

        # Тип контрагента
        self.cmb_tenant_kind = QComboBox()
        self.cmb_tenant_kind.addItem("Юридическое лицо", "legal")
        self.cmb_tenant_kind.addItem("Физическое лицо", "person")
        idx_kind = self.cmb_tenant_kind.findData(self._tenant_kind_in)
        self.cmb_tenant_kind.setCurrentIndex(idx_kind if idx_kind >= 0 else 0)
        self.cmb_tenant_kind.currentIndexChanged.connect(self._apply_kind_ui)

        # Тип аренды
        self.cmb_rent_kind = QComboBox()
        self.cmb_rent_kind.addItem("Долгосрочно", "long_term")
        self.cmb_rent_kind.addItem("Разово", "one_time")
        idx_rent = self.cmb_rent_kind.findData(self._rent_kind_in)
        self.cmb_rent_kind.setCurrentIndex(idx_rent if idx_rent >= 0 else 0)

        # ---- widgets (только юрлицо)
        self.ed_inn = QLineEdit(self._data_in.get("inn", "") or "")
        self.ed_email = QLineEdit(self._data_in.get("email", "") or "")

        self.ed_contact_name = QLineEdit(self._data_in.get("contact_name", "") or "")
        self.ed_contract_no = QLineEdit(self._data_in.get("contract_no", "") or "")

        # Вид обязательств (multi) — нужен и для физлица тоже
        self.cmb_obligation = QComboBox()
        self._setup_multiselect_combobox(self.cmb_obligation, _OBLIGATION_OPTIONS)
        self._set_multiselect_from_string(self.cmb_obligation, self._data_in.get("obligation_kind", "") or "")

        # Способ передачи документов (single) — только юрлицо
        self.cmb_delivery = QComboBox()
        self.cmb_delivery.addItems(_DELIVERY_OPTIONS)
        self._set_combobox_text(self.cmb_delivery, (self._data_in.get("docs_delivery_method", "") or "").strip())

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

        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")
        self.ed_notes = QTextEdit(self._data_in.get("notes", "") or "")

        # ---- group: Основное (общие поля)
        gb_main = QGroupBox("Основное")
        fm_main = QFormLayout(gb_main)
        fm_main.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fm_main.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        fm_main.setHorizontalSpacing(12)
        fm_main.setVerticalSpacing(10)

        fm_main.addRow("ФИО / Название *:", self.ed_name)
        fm_main.addRow("Тип контрагента:", self.cmb_tenant_kind)
        fm_main.addRow("Тип аренды:", self.cmb_rent_kind)
        fm_main.addRow("Телефон:", self.ed_phone)
        fm_main.addRow("Вид обязательств:", self.cmb_obligation)

        # ---- group: Реквизиты (юрлицо) — отдельный контейнер, чтобы скрывать красиво
        self.gb_legal = QGroupBox("Реквизиты (юрлицо)")
        fm_legal = QFormLayout(self.gb_legal)
        fm_legal.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fm_legal.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        fm_legal.setHorizontalSpacing(12)
        fm_legal.setVerticalSpacing(10)

        fm_legal.addRow("ИНН:", self.ed_inn)
        fm_legal.addRow("Email:", self.ed_email)

        # ---- group: Договор / реквизиты (юрлицо)
        self.gb_contract = QGroupBox("Договор")
        grid = QGridLayout(self.gb_contract)
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

        grid.addWidget(QLabel("Способ передачи документов:"), 3, 0)
        grid.addWidget(self.cmb_delivery, 3, 1, 1, 3)

        grid.addWidget(QLabel("Статус:"), 4, 0)
        grid.addWidget(self.cmb_status, 4, 1)

        # ---- group: Комментарии / примечания (общие)
        gb_notes = QGroupBox("Комментарии")
        fm_notes = QFormLayout(gb_notes)
        fm_notes.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        fm_notes.setHorizontalSpacing(12)
        fm_notes.setVerticalSpacing(10)
        fm_notes.addRow("Комментарий:", self.ed_comment)
        fm_notes.addRow("Примечания:", self.ed_notes)

        # ---- group: Правила расписания (общие)
        gb_rules = QGroupBox("Правила расписания")
        rules_layout = QVBoxLayout(gb_rules)
        rules_layout.setContentsMargins(12, 16, 12, 12)

        # Contract_from/contract_to для правил: если юрлицо — из договора, если физлицо — можно оставить пусто
        contract_from = _qdate_to_pydate(self.dt_valid_from.date())
        contract_to = _qdate_to_pydate(self.dt_valid_to.date())

        self.rules_widget = TenantRulesWidget(
            self,
            tenant_id=self._tenant_id,
            contract_from=contract_from,
            contract_to=contract_to,
            tenant_kind=self.cmb_tenant_kind.currentData(),  # NEW
            is_admin=self._is_admin,
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
        right_col.addWidget(self.gb_legal)
        right_col.addWidget(self.gb_contract)
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

        self._apply_kind_ui()

    def _apply_kind_ui(self) -> None:
        is_person = (self.cmb_tenant_kind.currentData() == "person")
        self.gb_legal.setVisible(not is_person)
        self.gb_contract.setVisible(not is_person)
    
        # NEW: чтобы дефолт для новых правил менялся сразу
        if hasattr(self, "rules_widget") and hasattr(self.rules_widget, "set_tenant_kind"):
            self.rules_widget.set_tenant_kind(self.cmb_tenant_kind.currentData())


    # ---------- helpers for multiselect combobox ----------

    def _setup_multiselect_combobox(self, cmb: QComboBox, options: List[str]) -> None:
        """
        Делает QComboBox с чекбоксами (множественный выбор).
        Выбор хранится в checkState элементов модели.
        """
        cmb.clear()
        cmb.setEditable(True)
        cmb.lineEdit().setReadOnly(True)
        cmb.lineEdit().setPlaceholderText("Выберите...")

        for opt in options:
            cmb.addItem(opt)
            idx = cmb.model().index(cmb.count() - 1, 0)
            cmb.model().setData(idx, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)

        cmb.view().pressed.connect(lambda mi: self._toggle_combo_checkstate(cmb, mi))
        self._refresh_multiselect_text(cmb)

    def _toggle_combo_checkstate(self, cmb: QComboBox, model_index) -> None:
        state = cmb.model().data(model_index, Qt.ItemDataRole.CheckStateRole)
        new_state = Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
        cmb.model().setData(model_index, new_state, Qt.ItemDataRole.CheckStateRole)
        self._refresh_multiselect_text(cmb)

    def _refresh_multiselect_text(self, cmb: QComboBox) -> None:
        selected = self._multiselect_values(cmb)
        cmb.lineEdit().setText(", ".join(selected))

    def _multiselect_values(self, cmb: QComboBox) -> List[str]:
        out: List[str] = []
        for i in range(cmb.count()):
            idx = cmb.model().index(i, 0)
            state = cmb.model().data(idx, Qt.ItemDataRole.CheckStateRole)
            if state == Qt.CheckState.Checked:
                out.append(cmb.itemText(i))
        return out

    def _set_multiselect_from_string(self, cmb: QComboBox, s: str) -> None:
        raw = (s or "").strip()
        if not raw:
            self._refresh_multiselect_text(cmb)
            return

        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        want = set(parts)

        for i in range(cmb.count()):
            text = cmb.itemText(i)
            idx = cmb.model().index(i, 0)
            cmb.model().setData(
                idx,
                Qt.CheckState.Checked if text in want else Qt.CheckState.Unchecked,
                Qt.ItemDataRole.CheckStateRole,
            )
        self._refresh_multiselect_text(cmb)

    @staticmethod
    def _set_combobox_text(cmb: QComboBox, text: str) -> None:
        if not text:
            cmb.setCurrentIndex(0)
            return
        idx = cmb.findText(text, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            cmb.setCurrentIndex(idx)
        else:
            cmb.addItem(text)
            cmb.setCurrentIndex(cmb.count() - 1)

    # ---------- end helpers ----------

    def _mk_date(self, d: Optional[date]) -> QDateEdit:
        w = QDateEdit()
        w.setCalendarPopup(True)
        w.setDisplayFormat("dd.MM.yyyy")
        w.setMinimumDate(QDate(1900, 1, 1))

        if d:
            w.setDate(_pydate_to_qdate(d))
        else:
            w.setDate(QDate.currentDate())

        return w

    def _on_accept(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Контрагент", "Введите ФИО/название.")
            self.ed_name.setFocus()
            return

        is_person = (self.cmb_tenant_kind.currentData() == "person")
        if not is_person:
            d_from = _qdate_to_pydate(self.dt_valid_from.date())
            d_to = _qdate_to_pydate(self.dt_valid_to.date())
            if d_from and d_to and d_to < d_from:
                QMessageBox.warning(self, "Контрагент", "Срок действия: дата 'по' не может быть раньше даты 'с'.")
                return

        self.accept()

    def values(self) -> Dict:
        obligation_list = self._multiselect_values(self.cmb_obligation)
        obligation_str = ", ".join(obligation_list)

        tenant_kind = self.cmb_tenant_kind.currentData()
        rent_kind = self.cmb_rent_kind.currentData()
        is_person = (tenant_kind == "person")

        base = {
            "name": self.ed_name.text().strip(),
            "phone": self.ed_phone.text().strip(),
            "obligation_kind": obligation_str,
            "tenant_kind": tenant_kind,
            "rent_kind": rent_kind,
            "comment": self.ed_comment.toPlainText().strip(),
            "notes": self.ed_notes.toPlainText().strip(),
        }

        if is_person:
            # Минимальные поля, остальное чистим чтобы не было "хвостов"
            base.update(
                {
                    "inn": None,
                    "email": None,
                    "contact_name": None,
                    "contract_no": None,
                    "contract_date": None,
                    "contract_valid_from": None,
                    "contract_valid_to": None,
                    "docs_delivery_method": None,
                    "status": "active",
                    "contract_signed": False,
                    "attached_in_1c": False,
                    "has_ds": False,
                }
            )
            return base

        # Юрлицо
        base.update(
            {
                "inn": self.ed_inn.text().strip(),
                "email": self.ed_email.text().strip(),
                "contact_name": self.ed_contact_name.text().strip(),
                "contract_no": self.ed_contract_no.text().strip(),
                "contract_date": _qdate_to_pydate(self.dt_contract_date.date()),
                "contract_valid_from": _qdate_to_pydate(self.dt_valid_from.date()),
                "contract_valid_to": _qdate_to_pydate(self.dt_valid_to.date()),
                "docs_delivery_method": self.cmb_delivery.currentText().strip(),
                "status": self.cmb_status.currentData(),
                "contract_signed": False,
                "attached_in_1c": False,
                "has_ds": False,
            }
        )
        return base

    def rules_payload(self) -> list[dict]:
        """
        Правила, которые пользователь добавил/изменил/отключил в карточке.
        Сохранять их в БД нужно в TenantsPage после dlg.exec().
        """
        return self.rules_widget.rules_payload()
