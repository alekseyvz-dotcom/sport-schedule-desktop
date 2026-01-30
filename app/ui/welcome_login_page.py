# app/ui/welcome_login_page.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame

from app.ui.login_window import LoginWindow
from app.services.users_service import AuthUser


_WELCOME_QSS = """
QWidget#welcomeRoot {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #f8fafc, stop:1 #eef2ff);
}

QFrame#loginCard {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 16px;
}

QLabel#appTitle {
    color: #0f172a;
    font-size: 22px;
    font-weight: 800;
}

QLabel#appSubtitle {
    color: #475569;
}
"""


class WelcomeLoginPage(QWidget):
    logged_in = Signal(object)  # AuthUser

    def __init__(self):
        super().__init__()
        self.setObjectName("welcomeRoot")
        self.setStyleSheet(_WELCOME_QSS)

        # "карточка"
        card = QFrame(self)
        card.setObjectName("loginCard")
        card.setFixedWidth(460)

        title = QLabel("Sport Schedule")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        subtitle = QLabel("Войдите, чтобы продолжить работу")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.login = LoginWindow()
        self.login.logged_in.connect(self.logged_in)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(22, 22, 22, 18)
        card_lay.setSpacing(12)
        card_lay.addWidget(title)
        card_lay.addWidget(subtitle)
        card_lay.addSpacing(6)
        card_lay.addWidget(self.login)

        # центрирование
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addStretch(1)
        root.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)
