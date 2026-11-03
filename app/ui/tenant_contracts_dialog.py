from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app.services.tenant_contracts_service import add_contract, list_contracts


class NewContractDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Новый договор')
        form = QFormLayout(self)
        self.number = QLineEdit()
        form.addRow('Номер *:', self.number)
        self.dates = []
        for label in ('Дата договора *:', 'Действует с *:', 'Действует по *:'):
            edit = QDateEdit(QDate.currentDate())
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd.MM.yyyy')
            form.addRow(label, edit)
            self.dates.append(edit)
        self.signed = QCheckBox('Подписан')
        self.attached = QCheckBox('Прикреплён в 1С')
        self.ds = QCheckBox('ДС')
        for box in (self.signed, self.attached, self.ds):
            form.addRow(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class TenantContractsDialog(QDialog):
    def __init__(self, *, user_id, role_code, tenant_id, parent=None):
        super().__init__(parent)
        self.user_id, self.role_code, self.tenant_id = user_id, role_code, tenant_id
        self.setWindowTitle('История договоров')
        self.resize(850, 420)
        layout = QVBoxLayout(self)
        note = QLabel('Новый договор сохраняется сразу в историю. Поля основного договора в карточке и сроки правил автоматически не изменяются.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(['Номер', 'Дата', 'С', 'По', 'Подписан', 'В 1С', 'ДС', 'Источник'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton('Добавить договор')
        add.setEnabled(str(role_code or '').strip().lower() == 'admin')
        add.clicked.connect(self._add)
        close = QPushButton('Закрыть')
        close.clicked.connect(self.accept)
        row.addWidget(add)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self._reload()

    def _reload(self):
        try:
            rows = list_contracts(user_id=self.user_id, role_code=self.role_code, tenant_id=self.tenant_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Договоры', f'Не удалось загрузить историю: {exc}')
            return
        self.table.setRowCount(len(rows))
        def fmt(value):
            return value.strftime('%d.%m.%Y') if value else '—'
        def flag(value):
            return '—' if value is None else ('Да' if value else 'Нет')
        for i, r in enumerate(rows):
            cells = [r['contract_no'] or '—', fmt(r['contract_date']), fmt(r['valid_from']), fmt(r['valid_to']),
                     flag(r['contract_signed']), flag(r['attached_in_1c']), flag(r['has_ds']),
                     'Исходная запись' if r['is_legacy'] else 'Добавлен в историю']
            for j, value in enumerate(cells):
                self.table.setItem(i, j, QTableWidgetItem(value))

    def _add(self):
        dialog = NewContractDialog(self)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                values = [edit.date().toPython() for edit in dialog.dates]
                add_contract(user_id=self.user_id, role_code=self.role_code, tenant_id=self.tenant_id,
                             contract_no=dialog.number.text(), contract_date=values[0],
                             valid_from=values[1], valid_to=values[2],
                             contract_signed=dialog.signed.isChecked(),
                             attached_in_1c=dialog.attached.isChecked(), has_ds=dialog.ds.isChecked())
            except Exception as exc:
                QMessageBox.warning(self, 'Договор не сохранён', str(exc))
                continue
            self._reload()
            QMessageBox.information(self, 'Договор', 'Договор сохранён в историю. Основные поля карточки и правила не изменены.')
            break
