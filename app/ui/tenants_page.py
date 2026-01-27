from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QCheckBox
)

from app.services.tenants_service import list_tenants, create_tenant, update_tenant, set_tenant_active, Tenant
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

        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(["ID", "Название", "ИНН", "Телефон", "Email", "Активен", "Комментарий"])
        self.tbl.setSelectionBehavior(self.tbl.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(self.tbl.EditTrigger.NoEditTriggers)
        self.tbl.doubleClicked.connect(self._on_edit)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self.reload()

    def _selected_tenant(self) -> Tenant | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        t = self.tbl.item(row, 0).data(Qt.UserRole)
        return t

    def reload(self):
        try:
            tenants = list_tenants(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Арендаторы", f"Ошибка загрузки:\n{e}")
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
            self.tbl.setItem(r, 5, QTableWidgetItem("Да" if t.is_active else "Нет"))
            self.tbl.setItem(r, 6, QTableWidgetItem(t.comment or ""))

        self.tbl.resizeColumnsToContents()

    def _on_add(self):
        dlg = TenantDialog(self, title="Создать арендатора")
        res = dlg.exec()
        QMessageBox.information(self, "DEBUG", f"Dialog result={res} (Accepted={dlg.Accepted})")
        if res != dlg.Accepted:
            return
    
        data = dlg.values()
        QMessageBox.information(self, "DEBUG", f"values={data}")
    
        try:
            new_id = create_tenant(**data)
        except Exception as e:
            QMessageBox.critical(self, "Создать арендатора", f"Ошибка:\n{repr(e)}")
            return
    
        QMessageBox.information(self, "DEBUG", f"Inserted tenant id={new_id}")
        self.reload()

    def _on_edit(self):
        t = self._selected_tenant()
        if not t:
            QMessageBox.information(self, "Редактировать", "Выберите арендатора в списке.")
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
            },
        )
        if dlg.exec() != dlg.Accepted:
            return

        data = dlg.values()
        try:
            update_tenant(t.id, **data)
        except Exception as e:
            QMessageBox.critical(self, "Редактировать арендатора", f"Ошибка:\n{e}")
            return
        self.reload()

    def _on_toggle_active(self):
        t = self._selected_tenant()
        if not t:
            QMessageBox.information(self, "Архив", "Выберите арендатора в списке.")
            return

        try:
            set_tenant_active(t.id, not t.is_active)
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return
        self.reload()
