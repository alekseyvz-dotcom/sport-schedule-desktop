# app/ui/login_window.py
import os
import sys

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QHBoxLayout, QApplication,
    QCheckBox, QToolButton, QSizePolicy,
)

from app.services.users_service import authenticate, AuthUser
from app.settings_manager import get_remembered_login, set_remembered_login


_LOGIN_QSS = """
QWidget#loginForm { background: transparent; }

QLabel#logo { padding: 6px 0 0 0; }

QLabel#status {
    color: #fb7185;
    padding: 2px 2px;
    font-size: 12px;
}

QLabel#copyright {
    color: rgba(226, 232, 240, 0.45);
    padding: 8px 2px 2px 2px;
    font-size: 11px;
}

QLineEdit {
    color: rgba(255, 255, 255, 0.92);
    background: rgba(2, 6, 23, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
    padding: 10px 12px;
    min-height: 24px;
    selection-background-color: rgba(99, 102, 241, 0.55);
}
QLineEdit::placeholder { color: rgba(226, 232, 240, 0.45); }

QLineEdit:focus {
    background: rgba(2, 6, 23, 0.45);
    border: 1px solid rgba(99, 102, 241, 0.95);
}

QPushButton {
    border-radius: 12px;
    padding: 10px 14px;
    font-weight: 800;
    min-height: 38px;
}

QPushButton#primary {
    color: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(99, 102, 241, 0.75);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(99, 102, 241, 1.0),
        stop:1 rgba(34, 211, 238, 1.0)
    );
}
QPushButton#primary:hover {
    border-color: rgba(255, 255, 255, 0.22);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(129, 140, 248, 1.0),
        stop:1 rgba(34, 211, 238, 1.0)
    );
}
QPushButton#primary:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(79, 70, 229, 1.0),
        stop:1 rgba(6, 182, 212, 1.0)
    );
}

QPushButton#ghost {
    color: rgba(226, 232, 240, 0.80);
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14);
}
QPushButton#ghost:hover {
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.20);
}
QPushButton#ghost:pressed { background: rgba(255, 255, 255, 0.07); }

/* ---- Кнопка "глаз" для пароля ---- */
QToolButton#eyeToggle {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px;
    color: rgba(226, 232, 240, 0.70);
    font-size: 12px;
    font-weight: 700;
}
QToolButton#eyeToggle:hover {
    background: rgba(255, 255, 255, 0.10);
    color: rgba(255, 255, 255, 0.90);
}
QToolButton#eyeToggle:pressed {
    background: rgba(255, 255, 255, 0.06);
}

/* ---- Чекбокс "Запомнить меня" ---- */
QCheckBox#rememberMe {
    color: rgba(226, 232, 240, 0.72);
    spacing: 8px;
    font-size: 12px;
}
QCheckBox#rememberMe::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    background: rgba(11, 18, 32, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
QCheckBox#rememberMe::indicator:checked {
    background: rgba(99, 102, 241, 0.95);
    border-color: rgba(99, 102, 241, 0.95);
}
QCheckBox#rememberMe::indicator:hover {
    border-color: rgba(255, 255, 255, 0.30);
}
"""


def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)


class LoginWindow(QWidget):
    logged_in = Signal(object)  # AuthUser

    def __init__(self):
        super().__init__()
        self.setObjectName("loginForm")
        self.setStyleSheet(_LOGIN_QSS)

        # ---- Logo ----
        self.lbl_logo = QLabel()
        self.lbl_logo.setObjectName("logo")
        self.lbl_logo.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        logo_path = resource_path(os.path.join("assets", "logo.png"))
        pix = QPixmap(logo_path)

        if not pix.isNull():
            pix = pix.scaledToWidth(140, Qt.SmoothTransformation)
            self.lbl_logo.setPixmap(pix)
        else:
            self.lbl_logo.setVisible(False)

        # ---- Inputs ----
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("status")

        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("Логин")
        self.ed_user.setClearButtonEnabled(True)

        self.ed_pass = QLineEdit()
        self.ed_pass.setPlaceholderText("Пароль")
        self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_pass.setClearButtonEnabled(True)

        # ---- Кнопка "глаз" — отдельная QToolButton справа от поля пароля ----
        self._pass_visible = False

        self._eye_on_icon = QIcon(resource_path(os.path.join("assets", "icons", "eye.png")))
        self._eye_off_icon = QIcon(resource_path(os.path.join("assets", "icons", "eye-off.png")))

        self.btn_eye = QToolButton()
        self.btn_eye.setObjectName("eyeToggle")
        self.btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eye.setFixedSize(36, 36)
        self.btn_eye.setToolTip("Показать/скрыть пароль")
        self.btn_eye.clicked.connect(self._toggle_password_visibility)

        # Устанавливаем начальную иконку/текст
        if not self._eye_off_icon.isNull():
            self.btn_eye.setIcon(self._eye_off_icon)
            self.btn_eye.setIconSize(self.btn_eye.size() * 0.55)
        else:
            self.btn_eye.setText("👁")

        # Поле пароля + глаз в одной строке
        pass_row = QHBoxLayout()
        pass_row.setContentsMargins(0, 0, 0, 0)
        pass_row.setSpacing(6)
        pass_row.addWidget(self.ed_pass, 1)
        pass_row.addWidget(self.btn_eye, 0)

        # ---- Чекбокс "Запомнить меня" ----
        self.chk_remember = QCheckBox("Запомнить меня")
        self.chk_remember.setObjectName("rememberMe")

        # ---- Buttons ----
        self.btn_login = QPushButton("Войти")
        self.btn_login.setObjectName("primary")
        self.btn_login.clicked.connect(self._on_login)

        self.btn_exit = QPushButton("Выход")
        self.btn_exit.setObjectName("ghost")
        self.btn_exit.clicked.connect(QApplication.quit)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addWidget(self.btn_exit)
        btns.addStretch(1)
        btns.addWidget(self.btn_login)

        # ---- Copyright ----
        self.lbl_copyright = QLabel("Разработал Алексей Зезюкин")
        self.lbl_copyright.setObjectName("copyright")
        self.lbl_copyright.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        # ---- Layout ----
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self.lbl_logo)
        root.addWidget(self.ed_user)
        root.addLayout(pass_row)
        root.addWidget(self.chk_remember)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)
        root.addWidget(self.lbl_copyright)

        self.ed_user.returnPressed.connect(self._on_login)
        self.ed_pass.returnPressed.connect(self._on_login)

        # ---- Восстановить сохранённый логин/пароль ----
        self._restore_remembered()

    def _restore_remembered(self):
        try:
            usr, pwd = get_remembered_login()
            if usr:
                self.ed_user.setText(usr)
                self.ed_pass.setText(pwd)
                self.chk_remember.setChecked(True)
                # Фокус на кнопку "Войти", чтобы можно было сразу Enter
                self.btn_login.setFocus()
        except Exception:
            pass  # если settings.dat повреждён — просто пустые поля

    def _toggle_password_visibility(self):
        self._pass_visible = not self._pass_visible
        self.ed_pass.setEchoMode(
            QLineEdit.Normal if self._pass_visible else QLineEdit.Password
        )

        if self._pass_visible:
            if not self._eye_on_icon.isNull():
                self.btn_eye.setIcon(self._eye_on_icon)
            else:
                self.btn_eye.setText("🙈")
        else:
            if not self._eye_off_icon.isNull():
                self.btn_eye.setIcon(self._eye_off_icon)
            else:
                self.btn_eye.setText("👁")

    def _on_login(self):
        self.lbl_status.setText("")
        u = self.ed_user.text().strip()
        p = self.ed_pass.text()
        remember = self.chk_remember.isChecked()

        try:
            auth_user = authenticate(u, p)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка подключения/запроса к БД:\n{e}")
            return

        if not auth_user:
            self.lbl_status.setText("Неверный логин/пароль или пользователь неактивен.")
            return

        # Сохраняем или очищаем запомненные данные
        try:
            set_remembered_login(u, p, remember)
        except Exception:
            pass  # не критично

        self.logged_in.emit(auth_user)
