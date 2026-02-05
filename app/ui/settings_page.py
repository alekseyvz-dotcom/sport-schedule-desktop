from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QMessageBox, QLineEdit
)

from app.services.users_service import AuthUser
from app.services.users_admin_service import (
    list_users, create_user, update_user, set_password,
    list_roles, list_org_permissions, save_org_permissions,
    user_tabs_summary, list_tab_permissions, save_tab_permissions,
    OrgPermRow, AdminUserRow, RoleRow
)
from app.ui.settings_user_dialogs import UserEditDialog, PasswordDialog, OrgPermissionsDialog, TabsPermissionsDialog


class SettingsPage(QWidget):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.user = user

        if (self.user.role_code or "").lower() != "admin":
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Доступ запрещён"))
            return

        self._roles: List[RoleRow] = []
        self._show_inactive_orgs: bool = False
        self._all_users: List[AdminUserRow] = []

        title = QLabel("Настройки — Пользователи")
        title.setObjectName("sectionTitle")

        self.ed_search_user = QLineEdit()
        self.ed_search_user.setPlaceholderText("Поиск пользователя (логин/ФИО)…")
        self.ed_search_user.textChanged.connect(self._apply_user_filter)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["id", "Логин", "ФИО", "Роль", "Активен", "Разделы"])
        self.tbl.setColumnHidden(0, True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        self.btn_add = QPushButton("Создать…")
        self.btn_edit = QPushButton("Редактировать…")
        self.btn_password = QPushButton("Сменить пароль…")
        self.btn_perms = QPushButton("Права на учреждения…")
        self.btn_tabs = QPushButton("Права на разделы…")
        self.btn_refresh = QPushButton("Обновить")

        self.btn_add.clicked.connect(self._add_user)
        self.btn_edit.clicked.connect(self._edit_user)
        self.btn_password.clicked.connect(self._change_password)
        self.btn_perms.clicked.connect(self._edit_org_perms)
        self.btn_tabs.clicked.connect(self._edit_tabs_perms)
        self.btn_refresh.clicked.connect(self.reload)
        
        btns = QHBoxLayout()
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_edit)
        btns.addWidget(self.btn_password)
        btns.addWidget(self.btn_perms)
        btns.addWidget(self.btn_tabs)
        btns.addStretch(1)
        btns.addWidget(self.btn_refresh)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(title)
        root.addWidget(self.ed_search_user)
        root.addLayout(btns)
        root.addWidget(self.tbl, 1)

        self.reload()

    def _selected_user(self) -> Optional[AdminUserRow]:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        return AdminUserRow(
            id=int(self.tbl.item(row, 0).text()),
            username=str(self.tbl.item(row, 1).text()),
            full_name=str(self.tbl.item(row, 2).text() or ""),
            role_code=str(self.tbl.item(row, 3).text()),
            is_active=(self.tbl.item(row, 4).text() == "Да"),
        )

    def reload(self):
        try:
            self._roles = list_roles()
            self._all_users = list_users()
        except Exception as e:
            QMessageBox.critical(self, "Пользователи", f"Ошибка загрузки:\n{e}")
            return

        self._render_users(self._all_users)
        self._apply_user_filter()

    def _render_users(self, users: List[AdminUserRow]):
        self.tbl.setRowCount(len(users))
        for i, u in enumerate(users):
            self.tbl.setItem(i, 0, QTableWidgetItem(str(u.id)))
            self.tbl.setItem(i, 1, QTableWidgetItem(u.username))
            self.tbl.setItem(i, 2, QTableWidgetItem(u.full_name))
            self.tbl.setItem(i, 3, QTableWidgetItem(u.role_code))
            self.tbl.setItem(i, 4, QTableWidgetItem("Да" if u.is_active else "Нет"))
            self.tbl.setItem(i, 5, QTableWidgetItem("Все" if u.role_code.lower() == "admin" else user_tabs_summary(u.id)))
        if users:
            self.tbl.selectRow(0)

    def _apply_user_filter(self):
        q = (self.ed_search_user.text() or "").strip().lower()
        for r in range(self.tbl.rowCount()):
            login = (self.tbl.item(r, 1).text() or "").lower()
            fio = (self.tbl.item(r, 2).text() or "").lower()
            hide = bool(q) and (q not in login) and (q not in fio)
            self.tbl.setRowHidden(r, hide)

    def _add_user(self):
        dlg = UserEditDialog(
            self,
            title="Создать пользователя",
            roles=self._roles,
            initial=None,
            username_readonly=False,
            ask_password=True,
            current_admin_user_id=int(self.user.id),
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        data = dlg.values()
        try:
            user_id = create_user(
                username=data["username"],
                password=data["password"],
                full_name=data.get("full_name", ""),
                role_code=data["role_code"],
                is_active=data["is_active"],
            )
            QMessageBox.information(self, "Готово", f"Создан пользователь id={user_id}")
            self.reload()
        except Exception as e:
            QMessageBox.critical(self, "Создать пользователя", str(e))

    def _edit_user(self):
        u = self._selected_user()
        if not u:
            QMessageBox.information(self, "Пользователи", "Выберите пользователя.")
            return

        dlg = UserEditDialog(
            self,
            title="Редактировать пользователя",
            roles=self._roles,
            initial={
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "role_code": u.role_code,
                "is_active": u.is_active,
            },
            username_readonly=True,
            ask_password=False,
            current_admin_user_id=int(self.user.id),
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        data = dlg.values()
        try:
            update_user(
                user_id=u.id,
                full_name=data.get("full_name", ""),
                role_code=data["role_code"],
                is_active=data["is_active"],
            )
            QMessageBox.information(self, "Готово", "Пользователь сохранён")
            self.reload()
        except Exception as e:
            QMessageBox.critical(self, "Редактировать пользователя", str(e))

    def _change_password(self):
        u = self._selected_user()
        if not u:
            QMessageBox.information(self, "Пользователи", "Выберите пользователя.")
            return

        dlg = PasswordDialog(self, title=f"Сменить пароль — {u.username}")
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        pw = dlg.password()
        try:
            set_password(u.id, pw)
            QMessageBox.information(self, "Готово", "Пароль изменён")
        except Exception as e:
            QMessageBox.critical(self, "Сменить пароль", str(e))

    def _edit_org_perms(self):
        u = self._selected_user()
        if not u:
            QMessageBox.information(self, "Пользователи", "Выберите пользователя.")
            return
    
        try:
            perms = list_org_permissions(u.id)   # <-- теперь всегда все
        except Exception as e:
            QMessageBox.critical(self, "Права", f"Ошибка загрузки прав:\n{e}")
            return
    
        dlg = OrgPermissionsDialog(
            self,
            title=f"Права на учреждения — {u.username}",
            perms=perms,
            show_inactive=self._show_inactive_orgs,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            self._show_inactive_orgs = dlg.show_inactive()
            return
    
        self._show_inactive_orgs = dlg.show_inactive()
        new_perms = dlg.perms()
    
        try:
            save_org_permissions(u.id, new_perms)
            QMessageBox.information(self, "Готово", "Права сохранены")
        except Exception as e:
            QMessageBox.critical(self, "Права", str(e))

    def _edit_tabs_perms(self):
        u = self._selected_user()
        if not u:
            QMessageBox.information(self, "Пользователи", "Выберите пользователя.")
            return
    
        if u.role_code.lower() == "admin":
            QMessageBox.information(self, "Разделы", "Администратору доступны все разделы.")
            return
    
        try:
            perms = list_tab_permissions(u.id)
        except Exception as e:
            QMessageBox.critical(self, "Разделы", f"Ошибка загрузки прав:\n{e}")
            return
    
        dlg = TabsPermissionsDialog(self, f"Права на разделы — {u.username}", perms)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
    
        try:
            save_tab_permissions(u.id, dlg.perms())
            QMessageBox.information(self, "Готово", "Права на разделы сохранены")
            self.reload()
        except Exception as e:
            QMessageBox.critical(self, "Разделы", str(e))


