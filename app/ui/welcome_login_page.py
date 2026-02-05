# app/ui/welcome_login_page.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QGraphicsDropShadowEffect

from app.ui.login_window import LoginWindow
from app.services.users_service import AuthUser


_WELCOME_QSS = """
QWidget#welcomeRoot {
    /* Глубокий, но спокойный фон */
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0b1220,
        stop:0.45 #111b33,
        stop:1 #0b1220
    );
}

/* Декоративные "пятна" на фоне */
QFrame#blobA {
    background: qradialgradient(cx:0.3, cy:0.3, radius:0.9,
        stop:0 rgba(99, 102, 241, 170),
        stop:0.35 rgba(99, 102, 241, 80),
        stop:1 rgba(99, 102, 241, 0)
    );
    border-radius: 260px;
}
QFrame#blobB {
    background: qradialgradient(cx:0.7, cy:0.6, radius:1.0,
        stop:0 rgba(34, 211, 238, 150),
        stop:0.35 rgba(34, 211, 238, 70),
        stop:1 rgba(34, 211, 238, 0)
    );
    border-radius: 300px;
}

/* Свечение под карточкой */
QFrame#glowLayer {
    background: qradialgradient(cx:0.5, cy:0.35, radius:0.9,
        stop:0 rgba(99, 102, 241, 190),
        stop:0.3 rgba(34, 211, 238, 120),
        stop:0.75 rgba(255, 255, 255, 18),
        stop:1 rgba(255, 255, 255, 0)
    );
    border-radius: 28px;
}

/* Стеклянная карточка */
QFrame#loginCard {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 22px;
}

/* Внутренняя "плашка", чтобы контент читался ещё лучше */
QFrame#cardInner {
    background: rgba(15, 23, 42, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 18px;
}

QLabel#appTitle {
    color: rgba(255, 255, 255, 0.94);
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 0.6px;
}

QLabel#appSubtitle {
    color: rgba(226, 232, 240, 0.78);
    font-size: 13px;
}

/* Небольшая подпись снизу (опционально) */
QLabel#hint {
    color: rgba(226, 232, 240, 0.55);
    font-size: 11px;
}
"""


class WelcomeLoginPage(QWidget):
    logged_in = Signal(object)  # AuthUser

    def __init__(self):
        super().__init__()
        self.setObjectName("welcomeRoot")
        self.setStyleSheet(_WELCOME_QSS)

        # --- Фоновые "пятна" (декор) ---
        blob_a = QFrame(self)
        blob_a.setObjectName("blobA")
        blob_a.setFixedSize(520, 520)
        blob_a.move(-140, -160)
        blob_a.lower()

        blob_b = QFrame(self)
        blob_b.setObjectName("blobB")
        blob_b.setFixedSize(600, 600)
        blob_b.move(420, 140)
        blob_b.lower()

        # --- Свечение под карточкой ---
        glow = QFrame(self)
        glow.setObjectName("glowLayer")
        glow.setFixedSize(520, 420)
        glow.lower()

        # --- Карточка ---
        card = QFrame(self)
        card.setObjectName("loginCard")
        card.setFixedWidth(480)

        # Тень карточки (даёт "премиум" ощущение глубины)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 18)
        shadow.setColor(QColor(0, 0, 0, 140))
        card.setGraphicsEffect(shadow)

        # Внутренняя область (повышаем читабельность)
        inner = QFrame(card)
        inner.setObjectName("cardInner")

        title = QLabel("ИАС ФУТБОЛ")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        subtitle = QLabel("Войдите, чтобы продолжить работу")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.login = LoginWindow()
        self.login.logged_in.connect(self.logged_in)

        hint = QLabel("Совет: используйте корпоративный логин и пароль")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(22, 20, 22, 18)
        inner_lay.setSpacing(12)
        inner_lay.addWidget(title)
        inner_lay.addWidget(subtitle)
        inner_lay.addSpacing(6)
        inner_lay.addWidget(self.login)
        inner_lay.addSpacing(6)
        inner_lay.addWidget(hint)

        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 14, 14, 14)
        card_lay.addWidget(inner)

        # Центрирование
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.addStretch(1)
        root.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

        # Позиционируем glow по центру под карточкой
        # (после layout — просто двигаем при первом show/resize через resizeEvent)
        self._card = card
        self._glow = glow

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Центрируем glow относительно карточки, чуть выше центра для "хайлайта"
        card_geo = self._card.geometry()
        glow_w = self._glow.width()
        glow_h = self._glow.height()
        x = card_geo.center().x() - glow_w // 2
        y = card_geo.center().y() - glow_h // 2 - 20
        self._glow.move(x, y)
        self._glow.lower()
