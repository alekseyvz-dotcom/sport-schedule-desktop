from __future__ import annotations

from typing import Optional, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QListWidget, QListWidgetItem
)

from app.services.users_admin_service import OrgPermRow, RoleRow


_DIALOG_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #7fb3ff; }

QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 600;
    min-height: 34px;
}
QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
QPushButton:pressed { background: #eef1f5; }

QCheckBox { padding: 0 6px; }

QLabel#dlgTitle { color:#111111; font-weight:700; padding: 0 2px; }
QLabel#hint { color:#334155; padding: 0 2px; }

QListWidget {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
}
QListWidget::item { padding: 8px 10px; }
QListWidget::item:selected { background: rgba(127,179,255,60); color: #111111; }

QTableWidget {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    gridline-color: #e9edf3;
}
QHeaderView::section {
    background: #f6f7f9;
    color: #111111;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #e6e6e6;
    font-weight: 600;
}
QTableWidget::item { padding: 6px 10px; }
"""


class RoleSelectDialog(QDialog):
    """
    Выбор роли с названием + описанием.
    """
    ROLE_DESCRIPTIONS = {
        "admin": "Полный доступ: пользователи, учреждения, расписание, отчёты.",
        "user": "Ограниченный доступ: работа только с назначенными учреждениями.",
    }

    def __init__(self, parent, title: str, roles: List[RoleRow], current_code: Optional[str] = None):
        super().__init__(parent)
        self.setStyleSheet(_DIALOG_QSS)
        self.setWindowTitle(title)
        self.resize(520, 360)

        self._roles = roles

        lbl_title = QLabel(title)
        lbl_title.setObjectName("dlgTitle")

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск роли…")
        self.ed_search.textChanged.connect(self._apply_filter)

        self.lst = QListWidget()
        self.lbl_desc = QLabel("Выберите роль")
        self.lbl_desc.setObjectName("hint")
        self.lbl_desc.setWordWrap(True)

        self.btn_ok = QPushButton("Выбрать")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(lbl_title)
        root.addWidget(self.ed_search)
        root.addWidget(self.lst, 1)
        root.addWidget(self.lbl_desc)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.btn_ok)
        footer.addWidget(self.btn_cancel)
        root.addLayout(footer)

        self._load_list(current_code)

        self.lst.currentItemChanged.connect(self._update_desc)
        self._update_desc()

    def _load_list(self, current_code: Optional[str]):
        self.lst.clear()
        for r in self._roles:
            it = QListWidgetItem(f"{r.name}  ({r.code})")
            it.setData(Qt.ItemDataRole.UserRole, r.code)
            self.lst.addItem(it)
            if current_code and r.code == current_code:
                self.lst.setCurrentItem(it)

        if self.lst.currentRow() < 0 and self.lst.count() > 0:
            self.lst.setCurrentRow(0)

    def _apply_filter(self):
        q = (self.ed_search.text() or "").strip().lower()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            code = str(it.data(Qt.ItemDataRole.UserRole) or "")
            text = (it.text() or "").lower()
            it.setHidden(bool(q) and (q not in text) and (q not in code.lower()))

    def _update_desc(self):
        it = self.lst.currentItem()
        if not it:
            self.lbl_desc.setText("Выберите роль")
            return
        code = str(it.data(Qt.ItemDataRole.UserRole) or "")
        self.lbl_desc.setText(self.ROLE_DESCRIPTIONS.get(code, "Описание отсутствует."))

    def _on_ok(self):
        if not self.lst.currentItem():
            QMessageBox.warning(self, "Роль", "Выберите роль.")
            return
        self.accept()

    def role_code(self) -> str:
        it = self.lst.currentItem()
        return str(it.data(Qt.ItemDataRole.UserRole) or "") if it else ""


class UserEditDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        roles: List[RoleRow],
        initial: Optional[Dict] = None,
        username_readonly: bool = False,
        ask_password: bool = True,
        current_admin_user_id: Optional[int] = None,
    ):
        super().__init__(parent)
        self.setStyleSheet(_DIALOG_QSS)
        self.setWindowTitle(title)
        self.resize(560, 300)

        self.roles = roles
        self.ask_password = ask_password
        self.current_admin_user_id = current_admin_user_id

        self._initial_user_id = int(initial.get("id")) if initial and initial.get("id") is not None else None

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("dlgTitle")

        self.ed_username = QLineEdit()
        self.ed_full_name = QLineEdit()

        self.ed_role = QLineEdit()
        self.ed_role.setReadOnly(True)
        self.btn_pick_role = QPushButton("Выбрать роль…")
        self.btn_pick_role.clicked.connect(self._pick_role)

        self.ch_active = QCheckBox("Активен")
        self.ch_active.setChecked(True)

        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password2 = QLineEdit()
        self.ed_password2.setEchoMode(QLineEdit.EchoMode.Password)

        self.btn_ok = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(self.lbl_title)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Логин:"), 0)
        r1.addWidget(self.ed_username, 1)
        root.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("ФИО:"), 0)
        r2.addWidget(self.ed_full_name, 1)
        root.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Роль:"), 0)
        r3.addWidget(self.ed_role, 1)
        r3.addWidget(self.btn_pick_role, 0)
        r3.addWidget(self.ch_active, 0)
        root.addLayout(r3)

        if self.ask_password:
            r4 = QHBoxLayout()
            r4.addWidget(QLabel("Пароль:"), 0)
            r4.addWidget(self.ed_password, 1)
            root.addLayout(r4)

            r5 = QHBoxLayout()
            r5.addWidget(QLabel("Повтор:"), 0)
            r5.addWidget(self.ed_password2, 1)
            root.addLayout(r5)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.btn_ok)
        footer.addWidget(self.btn_cancel)
        root.addLayout(footer)

        # initial fill
        if initial:
            self.ed_username.setText(str(initial.get("username") or ""))
            self.ed_full_name.setText(str(initial.get("full_name") or ""))
            self.ch_active.setChecked(bool(initial.get("is_active", True)))

            role_code = str(initial.get("role_code") or "")
            self._set_role_code(role_code)

        if not self.ed_role.text().strip() and self.roles:
            self._set_role_code(self.roles[0].code)

        self.ed_username.setReadOnly(username_readonly)

    def _role_name(self, code: str) -> str:
        for r in self.roles:
            if r.code == code:
                return r.name
        return code

    def _set_role_code(self, code: str):
        self._role_code = str(code or "")
        self.ed_role.setText(f"{self._role_name(self._role_code)} ({self._role_code})")

    def _pick_role(self):
        dlg = RoleSelectDialog(self, "Выбор роли", self.roles, current_code=getattr(self, "_role_code", None))
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        self._set_role_code(dlg.role_code())

    def _on_ok(self):
        username = (self.ed_username.text() or "").strip()
        if not username:
            QMessageBox.warning(self, "Проверка", "Введите логин.")
            return

        role_code = getattr(self, "_role_code", "")
        if not role_code:
            QMessageBox.warning(self, "Проверка", "Выберите роль.")
            return

        # запрет деактивировать / снять admin у самого себя
        if self.current_admin_user_id is not None and self._initial_user_id == self.current_admin_user_id:
            if not self.ch_active.isChecked():
                QMessageBox.warning(self, "Ограничение", "Нельзя деактивировать самого себя.")
                return
            if role_code.lower() != "admin":
                QMessageBox.warning(self, "Ограничение", "Нельзя снять роль администратора у самого себя.")
                return

        if self.ask_password:
            pw1 = self.ed_password.text() or ""
            pw2 = self.ed_password2.text() or ""
            if not pw1:
                QMessageBox.warning(self, "Проверка", "Введите пароль.")
                return
            if pw1 != pw2:
                QMessageBox.warning(self, "Проверка", "Пароли не совпадают.")
                return

        self.accept()

    def values(self) -> Dict:
        out = {
            "username": (self.ed_username.text() or "").strip(),
            "full_name": (self.ed_full_name.text() or "").strip(),
            "role_code": getattr(self, "_role_code", ""),
            "is_active": bool(self.ch_active.isChecked()),
        }
        if self.ask_password:
            out["password"] = self.ed_password.text() or ""
        return out


class PasswordDialog(QDialog):
    def __init__(self, parent, title: str, *, forbid_self: bool = False):
        super().__init__(parent)
        self.setStyleSheet(_DIALOG_QSS)
        self.setWindowTitle(title)
        self.resize(520, 190)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("dlgTitle")

        self.ed_pw1 = QLineEdit()
        self.ed_pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pw2 = QLineEdit()
        self.ed_pw2.setEchoMode(QLineEdit.EchoMode.Password)

        self.btn_ok = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(self.lbl_title)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Новый пароль:"), 0)
        r1.addWidget(self.ed_pw1, 1)
        root.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Повтор:"), 0)
        r2.addWidget(self.ed_pw2, 1)
        root.addLayout(r2)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.btn_ok)
        footer.addWidget(self.btn_cancel)
        root.addLayout(footer)

    def _on_ok(self):
        pw1 = self.ed_pw1.text() or ""
        pw2 = self.ed_pw2.text() or ""
        if not pw1:
            QMessageBox.warning(self, "Проверка", "Введите пароль.")
            return
        if pw1 != pw2:
            QMessageBox.warning(self, "Проверка", "Пароли не совпадают.")
            return
        self.accept()

    def password(self) -> str:
        return self.ed_pw1.text() or ""


class OrgPermissionsDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        perms: List[OrgPermRow],
        *,
        only_active_orgs: bool = True,
    ):
        super().__init__(parent)
        self.setStyleSheet(_DIALOG_QSS)
        self.setWindowTitle(title)
        self.resize(820, 560)

        self._only_active_orgs = only_active_orgs
        self._all_perms = perms[:]  # текущий набор (получен из сервиса)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("dlgTitle")

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск учреждения…")
        self.ed_search.textChanged.connect(self._apply_filter)

        self.ch_only_active = QCheckBox("Только активные учреждения")
        self.ch_only_active.setChecked(only_active_orgs)
        self.ch_only_active.stateChanged.connect(self._active_toggle_changed)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["org_id", "Учреждение", "Просмотр", "Редактирование"])
        self.tbl.setColumnHidden(0, True)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        header = self.tbl.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.btn_all_view = QPushButton("Просмотр всем")
        self.btn_all_edit = QPushButton("Редактирование всем")
        self.btn_none = QPushButton("Снять все")
        self.btn_ok = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")

        self.btn_all_view.clicked.connect(lambda: self._set_all(view=True, edit=False))
        self.btn_all_edit.clicked.connect(lambda: self._set_all(view=True, edit=True))
        self.btn_none.clicked.connect(self._clear_all)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.ch_only_active, 0)

        footer = QHBoxLayout()
        footer.addWidget(self.btn_all_view)
        footer.addWidget(self.btn_all_edit)
        footer.addWidget(self.btn_none)
        footer.addStretch(1)
        footer.addWidget(self.btn_ok)
        footer.addWidget(self.btn_cancel)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(self.lbl_title)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)
        root.addLayout(footer)

        self._load(self._all_perms)
        self._apply_filter()

    # ---- data load/render

    def _load(self, perms: List[OrgPermRow]):
        self.tbl.setRowCount(len(perms))
        for r, p in enumerate(perms):
            self.tbl.setItem(r, 0, QTableWidgetItem(str(p.org_id)))
            self.tbl.setItem(r, 1, QTableWidgetItem(p.org_name))

            ch_view = QCheckBox()
            ch_view.setChecked(bool(p.can_view))
            self.tbl.setCellWidget(r, 2, ch_view)

            ch_edit = QCheckBox()
            ch_edit.setChecked(bool(p.can_edit))
            self.tbl.setCellWidget(r, 3, ch_edit)

            # если edit включили — view включаем автоматически
            def sync_view(_state, rr=r):
                cv: QCheckBox = self.tbl.cellWidget(rr, 2)  # type: ignore
                ce: QCheckBox = self.tbl.cellWidget(rr, 3)  # type: ignore
                if ce.isChecked() and not cv.isChecked():
                    cv.setChecked(True)

            ch_edit.stateChanged.connect(sync_view)

    def _apply_filter(self):
        q = (self.ed_search.text() or "").strip().lower()
        for r in range(self.tbl.rowCount()):
            name = (self.tbl.item(r, 1).text() or "").lower()
            hide = bool(q) and (q not in name)
            self.tbl.setRowHidden(r, hide)

    # ---- bulk actions

    def _set_all(self, *, view: bool, edit: bool):
        for r in range(self.tbl.rowCount()):
            cv: QCheckBox = self.tbl.cellWidget(r, 2)  # type: ignore
            ce: QCheckBox = self.tbl.cellWidget(r, 3)  # type: ignore
            cv.setChecked(view)
            ce.setChecked(edit)

    def _clear_all(self):
        for r in range(self.tbl.rowCount()):
            cv: QCheckBox = self.tbl.cellWidget(r, 2)  # type: ignore
            ce: QCheckBox = self.tbl.cellWidget(r, 3)  # type: ignore
            cv.setChecked(False)
            ce.setChecked(False)

    # ---- active toggle

    def _active_toggle_changed(self):
        # UI-тоггл меняет только состояние; данные перезагружает SettingsPage
        # Здесь просто подсказка пользователю.
        pass

    # ---- output

    def perms(self) -> List[OrgPermRow]:
        out: List[OrgPermRow] = []
        for r in range(self.tbl.rowCount()):
            org_id = int(self.tbl.item(r, 0).text())
            org_name = self.tbl.item(r, 1).text()
            cv: QCheckBox = self.tbl.cellWidget(r, 2)  # type: ignore
            ce: QCheckBox = self.tbl.cellWidget(r, 3)  # type: ignore
            out.append(OrgPermRow(org_id=org_id, org_name=org_name, can_view=cv.isChecked(), can_edit=ce.isChecked()))
        return out

    def only_active_orgs(self) -> bool:
        return bool(self.ch_only_active.isChecked())
