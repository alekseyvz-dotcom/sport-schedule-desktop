# app/ui/login_window.py
import os
import sys

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QHBoxLayout, QApplication
)

from app.services.users_service import authenticate, AuthUser


_LOGIN_QSS = """
QWidget#loginForm { background: transparent; }

QLabel#logo {
    padding: 8px 0 2px 0;
}

QLabel#status {
    color: #b00020;
    padding: 2px 2px;
}

QLabel#copyright {
    color: #64748b;
    padding: 6px 2px 2px 2px;
    font-size: 12px;
}

QLineEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 9px 12px;
    min-height: 22px;
}
QLineEdit:focus { border: 1px solid #7fb3ff; }

QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 9px 12px;
    font-weight: 700;
    min-height: 36px;
}
QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
QPushButton:pressed { background: #eef1f5; }

QPushButton#primary {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: white;
}
QPushButton#primary:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#primary:pressed { background: #1e40af; border-color: #1e40af; }

QPushButton#ghost {
    background: transparent;
    border: 1px solid #e6e6e6;
    color: #0f172a;
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

        # ---- Inputs & buttons ----
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("status")

        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("Логин")

        self.ed_pass = QLineEdit()
        self.ed_pass.setPlaceholderText("Пароль")
        self.ed_pass.setEchoMode(QLineEdit.Password)

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
        root.addWidget(self.lbl_copyright)  # <-- в самый низ

        self.ed_user.returnPressed.connect(self._on_login)
        self.ed_pass.returnPressed.connect(self._on_login)

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

        self.logged_in.emit(auth_user)
