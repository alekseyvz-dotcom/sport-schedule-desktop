# app/ui/settings_page.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QLabel, QMessageBox, QInputDialog
)

from app.services.users_service import AuthUser
from app.services.users_admin_service import (
    list_users, create_user, update_user, set_password,
    list_roles, list_org_permissions, save_org_permissions, OrgPermRow
)


class SettingsPage(QWidget):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.user = user

        if (self.user.role_code or "").lower() != "admin":
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Доступ запрещён"))
            return

        root = QHBoxLayout(self)

        # ---- LEFT: users
        left = QVBoxLayout()
        root.addLayout(left, 2)

        left.addWidget(QLabel("Пользователи"))

        self.tbl_users = QTableWidget(0, 5)
        self.tbl_users.setHorizontalHeaderLabels(["id", "Логин", "ФИО", "Роль", "Активен"])
        self.tbl_users.setColumnHidden(0, True)
        self.tbl_users.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_users.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_users.itemSelectionChanged.connect(self._on_user_selected)
        left.addWidget(self.tbl_users, 1)

        self.btn_add = QPushButton("Создать пользователя…")
        self.btn_add.clicked.connect(self._create_user)
        left.addWidget(self.btn_add)

        # ---- RIGHT: editor + perms
        right = QVBoxLayout()
        root.addLayout(right, 3)

        right.addWidget(QLabel("Параметры пользователя"))

        row = QHBoxLayout()
        self.ed_full_name = QLineEdit()
        self.cb_role = QComboBox()
        self.cb_active = QCheckBox("Активен")
        row.addWidget(QLabel("ФИО:"))
        row.addWidget(self.ed_full_name, 1)
        row.addWidget(QLabel("Роль:"))
        row.addWidget(self.cb_role)
        row.addWidget(self.cb_active)
        right.addLayout(row)

        btns = QHBoxLayout()
        self.btn_save_user = QPushButton("Сохранить пользователя")
        self.btn_save_user.clicked.connect(self._save_user)
        self.btn_password = QPushButton("Сменить пароль…")
        self.btn_password.clicked.connect(self._change_password)
        btns.addWidget(self.btn_save_user)
        btns.addWidget(self.btn_password)
        right.addLayout(btns)

        right.addWidget(QLabel("Права на учреждения"))

        self.tbl_orgs = QTableWidget(0, 4)
        self.tbl_orgs.setHorizontalHeaderLabels(["org_id", "Учреждение", "Просмотр", "Редактирование"])
        self.tbl_orgs.setColumnHidden(0, True)
        right.addWidget(self.tbl_orgs, 1)

        self.btn_save_perms = QPushButton("Сохранить права")
        self.btn_save_perms.clicked.connect(self._save_perms)
        right.addWidget(self.btn_save_perms)

        self._current_user_id: int | None = None

        self._load_roles()
        self._reload_users()

    def _load_roles(self):
        self.cb_role.clear()
        for r in list_roles():
            self.cb_role.addItem(r)

    def _reload_users(self):
        users = list_users()
        self.tbl_users.setRowCount(len(users))
        for i, u in enumerate(users):
            self.tbl_users.setItem(i, 0, QTableWidgetItem(str(u.id)))
            self.tbl_users.setItem(i, 1, QTableWidgetItem(u.username))
            self.tbl_users.setItem(i, 2, QTableWidgetItem(u.full_name))
            self.tbl_users.setItem(i, 3, QTableWidgetItem(u.role_code))
            self.tbl_users.setItem(i, 4, QTableWidgetItem("Да" if u.is_active else "Нет"))

        if users:
            self.tbl_users.selectRow(0)

    def _on_user_selected(self):
        row = self.tbl_users.currentRow()
        if row < 0:
            return
        user_id = int(self.tbl_users.item(row, 0).text())
        self._current_user_id = user_id

        full_name = self.tbl_users.item(row, 2).text()
        role_code = self.tbl_users.item(row, 3).text()
        is_active = (self.tbl_users.item(row, 4).text() == "Да")

        self.ed_full_name.setText(full_name)
        self.cb_role.setCurrentText(role_code)
        self.cb_active.setChecked(is_active)

        self._reload_org_perms(user_id)

    def _reload_org_perms(self, user_id: int):
        perms = list_org_permissions(user_id)
        self.tbl_orgs.setRowCount(len(perms))

        for r, p in enumerate(perms):
            self.tbl_orgs.setItem(r, 0, QTableWidgetItem(str(p.org_id)))
            self.tbl_orgs.setItem(r, 1, QTableWidgetItem(p.org_name))

            ch_view = QCheckBox()
            ch_view.setChecked(p.can_view)
            self.tbl_orgs.setCellWidget(r, 2, ch_view)

            ch_edit = QCheckBox()
            ch_edit.setChecked(p.can_edit)
            self.tbl_orgs.setCellWidget(r, 3, ch_edit)

    def _save_user(self):
        if self._current_user_id is None:
            return
        try:
            update_user(
                user_id=self._current_user_id,
                full_name=self.ed_full_name.text().strip(),
                role_code=self.cb_role.currentText(),
                is_active=self.cb_active.isChecked(),
            )
            QMessageBox.information(self, "Готово", "Пользователь сохранён")
            self._reload_users()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _change_password(self):
        if self._current_user_id is None:
            return
        pw, ok = QInputDialog.getText(self, "Сменить пароль", "Новый пароль:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            set_password(self._current_user_id, pw)
            QMessageBox.information(self, "Готово", "Пароль изменён")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _save_perms(self):
        if self._current_user_id is None:
            return

        perms: list[OrgPermRow] = []
        for r in range(self.tbl_orgs.rowCount()):
            org_id = int(self.tbl_orgs.item(r, 0).text())
            org_name = self.tbl_orgs.item(r, 1).text()
            ch_view: QCheckBox = self.tbl_orgs.cellWidget(r, 2)  # type: ignore
            ch_edit: QCheckBox = self.tbl_orgs.cellWidget(r, 3)  # type: ignore

            perms.append(
                OrgPermRow(
                    org_id=org_id,
                    org_name=org_name,
                    can_view=ch_view.isChecked(),
                    can_edit=ch_edit.isChecked(),
                )
            )

        try:
            save_org_permissions(self._current_user_id, perms)
            QMessageBox.information(self, "Готово", "Права сохранены")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _create_user(self):
        username, ok = QInputDialog.getText(self, "Создать пользователя", "Логин:")
        if not ok:
            return
        password, ok = QInputDialog.getText(self, "Создать пользователя", "Пароль:", QLineEdit.EchoMode.Password)
        if not ok:
            return

        full_name, _ = QInputDialog.getText(self, "Создать пользователя", "ФИО (необязательно):")
        role_code = self.cb_role.currentText() or "user"

        try:
            user_id = create_user(username=username, password=password, full_name=full_name, role_code=role_code, is_active=True)
            QMessageBox.information(self, "Готово", f"Создан пользователь id={user_id}")
            self._reload_users()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
