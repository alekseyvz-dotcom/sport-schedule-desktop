# app/ui/login_window.py
import os
import sys

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QHBoxLayout, QApplication
)

from app.services.users_service import authenticate, AuthUser


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

        # ---- Inputs & buttons ----
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("status")

        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("Логин")
        self.ed_user.setClearButtonEnabled(True)

        self.ed_pass = QLineEdit()
        self.ed_pass.setPlaceholderText("Пароль")
        self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_pass.setClearButtonEnabled(True)

        # --- “глаз” внутри поля пароля ---
        # Вариант A: если есть иконки в assets/icons:
        #   assets/icons/eye.png
        #   assets/icons/eye-off.png
        # Если нет — кнопка всё равно появится как текстовая (fallback).
        self._eye_on_icon = QIcon(resource_path(os.path.join("assets", "icons", "eye.png")))
        self._eye_off_icon = QIcon(resource_path(os.path.join("assets", "icons", "eye-off.png")))

        self._act_toggle_pass = self.ed_pass.addAction(
            self._eye_off_icon if not self._eye_off_icon.isNull() else QIcon(),
            QLineEdit.TrailingPosition
        )
        if self._eye_off_icon.isNull():
            self._act_toggle_pass.setText("Показать")

        self._act_toggle_pass.triggered.connect(self._toggle_password_visibility)
        self._pass_visible = False

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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(self.lbl_logo)
        root.addWidget(self.ed_user)
        root.addWidget(self.ed_pass)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)
        root.addWidget(self.lbl_copyright)

        self.ed_user.returnPressed.connect(self._on_login)
        self.ed_pass.returnPressed.connect(self._on_login)

    def _toggle_password_visibility(self):
        self._pass_visible = not self._pass_visible
        self.ed_pass.setEchoMode(QLineEdit.Normal if self._pass_visible else QLineEdit.Password)

        # Меняем иконку/текст
        if self._pass_visible:
            if not self._eye_on_icon.isNull():
                self._act_toggle_pass.setIcon(self._eye_on_icon)
            else:
                self._act_toggle_pass.setText("Скрыть")
        else:
            if not self._eye_off_icon.isNull():
                self._act_toggle_pass.setIcon(self._eye_off_icon)
            else:
                self._act_toggle_pass.setText("Показать")

    def _on_login(self):
        self.lbl_status.setText("")
        u = self.ed_user.text().strip()
        p = self.ed_pass.text()

        try:
            auth_user = authenticate(u, p)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка подключения/запроса к БД:\n{e}")
            return

        if not auth_user:
            self.lbl_status.setText("Неверный логин/пароль или пользователь неактивен.")
            return

        print("LOGIN OK, emit logged_in:", user.username)
        self.logged_in.emit(user)
