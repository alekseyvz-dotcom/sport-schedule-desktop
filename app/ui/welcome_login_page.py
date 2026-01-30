# app/ui/welcome_login_page.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from app.ui.login_window import LoginWindow
from app.services.users_service import AuthUser


class WelcomeLoginPage(QWidget):
    logged_in = Signal(object)  # AuthUser

    def __init__(self):
        super().__init__()

        title = QLabel("Добро пожаловать в ИАС ФУТБОЛ")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        subtitle = QLabel("Пожалуйста, войдите в систему.")
        subtitle.setStyleSheet("color: #666;")

        self.login = LoginWindow()
        self.login.logged_in.connect(self.logged_in)

        root = QVBoxLayout(self)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(12)
        root.addWidget(self.login)
        root.addStretch(1)
