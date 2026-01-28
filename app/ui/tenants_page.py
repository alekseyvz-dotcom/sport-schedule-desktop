from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QCheckBox,
)

from app.services.tenants_service import (
    Tenant,
    list_tenants,
    create_tenant,
    update_tenant,
    set_tenant_active,
)
from app.ui.tenant_dialog import TenantDialog


class TenantsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск: имя / ИНН / телефон")
        self.ed_search.returnPressed.connect(self.reload)

        self.cb_inactive = QCheckBox("Показывать архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)

        top = QHBoxLayout()
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        # Расширили таблицу, чтобы было видно часть полей карточки
        self.tbl = QTableWidget(0, 12)
        self.tbl.setHorizontalHeaderLabels(
            [
                "ID",
                "Название",
                "ИНН",
                "Телефон",
                "Email",
                "Контакт",
                "№ договора",
                "Срок с",
                "Срок по",
                "Статус",
                "Активен",
                "Комментарий",
            ]
        )
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.doubleClicked.connect(self._on_edit)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self.reload()

    def _selected_tenant(self) -> Tenant | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        item = self.tbl.item(row, 0)
        if not item:
            return None
        t = item.data(Qt.UserRole)
        return t if isinstance(t, Tenant) else None

    def reload(self):
        try:
            tenants = list_tenants(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Контрагенты", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for t in tenants:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(t.id))
            it_id.setData(Qt.UserRole, t)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, QTableWidgetItem(t.name))
            self.tbl.setItem(r, 2, QTableWidgetItem(t.inn or ""))
            self.tbl.setItem(r, 3, QTableWidgetItem(t.phone or ""))
            self.tbl.setItem(r, 4, QTableWidgetItem(t.email or ""))
            self.tbl.setItem(r, 5, QTableWidgetItem(t.contact_name or ""))
            self.tbl.setItem(r, 6, QTableWidgetItem(t.contract_no or ""))
            self.tbl.setItem(r, 7, QTableWidgetItem(f"{t.contract_valid_from:%d.%m.%Y}" if t.contract_valid_from else ""))
            self.tbl.setItem(r, 8, QTableWidgetItem(f"{t.contract_valid_to:%d.%m.%Y}" if t.contract_valid_to else ""))
            self.tbl.setItem(r, 9, QTableWidgetItem(t.status or ""))
            self.tbl.setItem(r, 10, QTableWidgetItem("Да" if t.is_active else "Нет"))
            self.tbl.setItem(r, 11, QTableWidgetItem(t.comment or ""))

        self.tbl.resizeColumnsToContents()

    def _on_add(self):
        dlg = TenantDialog(self, title="Создать контрагента")
        if dlg.exec() != dlg.Accepted:
            return

        data = dlg.values()

        try:
            new_id = create_tenant(**data)
        except Exception as e:
            QMessageBox.critical(self, "Создать контрагента", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Контрагенты", f"Создан контрагент (id={new_id}).")
        self.reload()
        self._select_row_by_id(new_id)

    def _on_edit(self):
        t = self._selected_tenant()
        if not t:
            QMessageBox.information(self, "Редактировать", "Выберите контрагента в списке.")
            return

        dlg = TenantDialog(
            self,
            title=f"Редактировать: {t.name}",
            data={
                "name": t.name,
                "inn": t.inn,
                "phone": t.phone,
                "email": t.email,
                "comment": t.comment,
                "contact_name": t.contact_name,
                "obligation_kind": t.obligation_kind,
                "contract_no": t.contract_no,
                "contract_date": t.contract_date,
                "contract_valid_from": t.contract_valid_from,
                "contract_valid_to": t.contract_valid_to,
                "docs_delivery_method": t.docs_delivery_method,
                "status": t.status,
                "contract_signed": t.contract_signed,
                "attached_in_1c": t.attached_in_1c,
                "has_ds": t.has_ds,
                "notes": t.notes,
            },
        )
        if dlg.exec() != dlg.Accepted:
            return

        data = dlg.values()
        try:
            update_tenant(t.id, **data)
        except Exception as e:
            QMessageBox.critical(self, "Редактировать контрагента", f"Ошибка:\n{e}")
            return

        self.reload()
        self._select_row_by_id(t.id)

    def _on_toggle_active(self):
        t = self._selected_tenant()
        if not t:
            QMessageBox.information(self, "Архив", "Выберите контрагента в списке.")
            return

        new_state = not t.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы действительно хотите {action} контрагента «{t.name}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_tenant_active(t.id, new_state)
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload()

    def _select_row_by_id(self, tenant_id: int) -> None:
        for r in range(self.tbl.rowCount()):
            item = self.tbl.item(r, 0)
            if not item:
                continue
            if item.text() == str(tenant_id):
                self.tbl.setCurrentCell(r, 0)
                self.tbl.scrollToItem(item)
                return
