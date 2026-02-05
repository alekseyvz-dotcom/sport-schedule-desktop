# app/ui/welcome_login_page.py
from PySide6.QtCore import (
    Qt, Signal, QEasingCurve, QPoint, QRect, QEvent,
    QPropertyAnimation, QParallelAnimationGroup
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)

from app.ui.login_window import LoginWindow
from app.services.users_service import AuthUser


_WELCOME_QSS = """
QWidget#welcomeRoot {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0b1220,
        stop:0.45 #111b33,
        stop:1 #0b1220
    );
}

QFrame#blobA {
    background: qradialgradient(cx:0.3, cy:0.3, radius:0.9,
        stop:0 rgba(99, 102, 241, 160),
        stop:0.35 rgba(99, 102, 241, 70),
        stop:1 rgba(99, 102, 241, 0)
    );
    border-radius: 260px;
}
QFrame#blobB {
    background: qradialgradient(cx:0.7, cy:0.6, radius:1.0,
        stop:0 rgba(34, 211, 238, 140),
        stop:0.35 rgba(34, 211, 238, 60),
        stop:1 rgba(34, 211, 238, 0)
    );
    border-radius: 300px;
}

QFrame#glowLayer {
    background: qradialgradient(cx:0.5, cy:0.35, radius:0.9,
        stop:0 rgba(99, 102, 241, 150),
        stop:0.32 rgba(34, 211, 238, 95),
        stop:0.78 rgba(255, 255, 255, 14),
        stop:1 rgba(255, 255, 255, 0)
    );
    border-radius: 28px;
}

QFrame#loginCard {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 22px;
}

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
        self.setMouseTracking(True)

        # Создаём login СРАЗУ (важно для eventFilter, чтобы не словить AttributeError)
        self.login = LoginWindow()
        self.login.logged_in.connect(self.logged_in)

        # --- Blobs ---
        self._blob_a = QFrame(self)
        self._blob_a.setObjectName("blobA")
        self._blob_a.setFixedSize(520, 520)
        self._blob_a.move(-140, -160)
        self._blob_a.lower()

        self._blob_b = QFrame(self)
        self._blob_b.setObjectName("blobB")
        self._blob_b.setFixedSize(600, 600)
        self._blob_b.move(420, 140)
        self._blob_b.lower()

        self._blob_a_op = QGraphicsOpacityEffect(self._blob_a)
        self._blob_a_op.setOpacity(1.0)
        self._blob_a.setGraphicsEffect(self._blob_a_op)

        self._blob_b_op = QGraphicsOpacityEffect(self._blob_b)
        self._blob_b_op.setOpacity(0.95)
        self._blob_b.setGraphicsEffect(self._blob_b_op)

        self._blob_a_base_pos = self._blob_a.pos()
        self._blob_b_base_pos = self._blob_b.pos()
        self._blob_a_base_geo = self._blob_a.geometry()
        self._blob_b_base_geo = self._blob_b.geometry()

        # --- Glow under card ---
        self._glow = QFrame(self)
        self._glow.setObjectName("glowLayer")
        self._glow.setFixedSize(520, 420)
        self._glow.lower()

        self._glow_op = QGraphicsOpacityEffect(self._glow)
        self._glow_op.setOpacity(0.78)
        self._glow.setGraphicsEffect(self._glow_op)

        # --- Card ---
        self._card = QFrame(self)
        self._card.setObjectName("loginCard")
        self._card.setFixedWidth(480)
        self._card.setAttribute(Qt.WA_Hover, True)

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 18)
        shadow.setColor(QColor(0, 0, 0, 140))
        self._card.setGraphicsEffect(shadow)

        inner = QFrame(self._card)
        inner.setObjectName("cardInner")

        title = QLabel("ИАС ФУТБОЛ")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        subtitle = QLabel("Войдите, чтобы продолжить работу")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)

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

        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(14, 14, 14, 14)
        card_lay.addWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.addStretch(1)
        root.addWidget(self._card, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

        # --- Card micro animation ---
        self._base_card_pos = None
        self._shadow = shadow

        self._hover_anim = QPropertyAnimation(self._card, b"pos", self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(180)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._glow_hover_op_anim = QPropertyAnimation(self._glow_op, b"opacity", self)
        self._glow_hover_op_anim.setDuration(180)
        self._glow_hover_op_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Ставим eventFilter ПОСЛЕ того как всё нужное создано
        self._card.installEventFilter(self)
        self.login.ed_user.installEventFilter(self)
        self.login.ed_pass.installEventFilter(self)

        # --- Premium background motion (super soft) ---
        self._start_premium_background_motion()

    def _start_premium_background_motion(self):
        def center_breathe(base: QRect, delta: int):
            a = QRect(base.x(), base.y(), base.width(), base.height())
            b = QRect(base.x() - delta // 2, base.y() - delta // 2, base.width() + delta, base.height() + delta)
            return a, b

        # Blob A
        d_a = 26
        ga0, ga1 = center_breathe(self._blob_a_base_geo, d_a)

        self._blob_a_pos_anim = QPropertyAnimation(self._blob_a, b"pos", self)
        self._blob_a_pos_anim.setDuration(16000)
        self._blob_a_pos_anim.setLoopCount(-1)
        self._blob_a_pos_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_a_pos_anim.setStartValue(self._blob_a_base_pos + QPoint(0, 0))
        self._blob_a_pos_anim.setKeyValueAt(0.35, self._blob_a_base_pos + QPoint(18, 10))
        self._blob_a_pos_anim.setKeyValueAt(0.70, self._blob_a_base_pos + QPoint(8, 22))
        self._blob_a_pos_anim.setEndValue(self._blob_a_base_pos + QPoint(0, 0))

        self._blob_a_geo_anim = QPropertyAnimation(self._blob_a, b"geometry", self)
        self._blob_a_geo_anim.setDuration(19000)
        self._blob_a_geo_anim.setLoopCount(-1)
        self._blob_a_geo_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_a_geo_anim.setStartValue(ga0)
        self._blob_a_geo_anim.setKeyValueAt(0.5, ga1)
        self._blob_a_geo_anim.setEndValue(ga0)

        self._blob_a_op_anim = QPropertyAnimation(self._blob_a_op, b"opacity", self)
        self._blob_a_op_anim.setDuration(21000)
        self._blob_a_op_anim.setLoopCount(-1)
        self._blob_a_op_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_a_op_anim.setStartValue(0.92)
        self._blob_a_op_anim.setKeyValueAt(0.5, 1.0)
        self._blob_a_op_anim.setEndValue(0.92)

        self._blob_a_group = QParallelAnimationGroup(self)
        self._blob_a_group.addAnimation(self._blob_a_pos_anim)
        self._blob_a_group.addAnimation(self._blob_a_geo_anim)
        self._blob_a_group.addAnimation(self._blob_a_op_anim)
        self._blob_a_group.start()

        # Blob B
        d_b = 34
        gb0, gb1 = center_breathe(self._blob_b_base_geo, d_b)

        self._blob_b_pos_anim = QPropertyAnimation(self._blob_b, b"pos", self)
        self._blob_b_pos_anim.setDuration(22000)
        self._blob_b_pos_anim.setLoopCount(-1)
        self._blob_b_pos_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_b_pos_anim.setStartValue(self._blob_b_base_pos + QPoint(0, 0))
        self._blob_b_pos_anim.setKeyValueAt(0.40, self._blob_b_base_pos + QPoint(-22, -12))
        self._blob_b_pos_anim.setKeyValueAt(0.75, self._blob_b_base_pos + QPoint(-10, -26))
        self._blob_b_pos_anim.setEndValue(self._blob_b_base_pos + QPoint(0, 0))

        self._blob_b_geo_anim = QPropertyAnimation(self._blob_b, b"geometry", self)
        self._blob_b_geo_anim.setDuration(24000)
        self._blob_b_geo_anim.setLoopCount(-1)
        self._blob_b_geo_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_b_geo_anim.setStartValue(gb0)
        self._blob_b_geo_anim.setKeyValueAt(0.5, gb1)
        self._blob_b_geo_anim.setEndValue(gb0)

        self._blob_b_op_anim = QPropertyAnimation(self._blob_b_op, b"opacity", self)
        self._blob_b_op_anim.setDuration(26000)
        self._blob_b_op_anim.setLoopCount(-1)
        self._blob_b_op_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_b_op_anim.setStartValue(0.86)
        self._blob_b_op_anim.setKeyValueAt(0.5, 0.96)
        self._blob_b_op_anim.setEndValue(0.86)

        self._blob_b_group = QParallelAnimationGroup(self)
        self._blob_b_group.addAnimation(self._blob_b_pos_anim)
        self._blob_b_group.addAnimation(self._blob_b_geo_anim)
        self._blob_b_group.addAnimation(self._blob_b_op_anim)
        self._blob_b_group.start()

        # Glow breathe (запускаем в resizeEvent, когда glow центрирован)
        self._glow_geo_anim = QPropertyAnimation(self._glow, b"geometry", self)
        self._glow_geo_anim.setDuration(12000)
        self._glow_geo_anim.setLoopCount(-1)
        self._glow_geo_anim.setEasingCurve(QEasingCurve.InOutSine)

        self._glow_op_anim = QPropertyAnimation(self._glow_op, b"opacity", self)
        self._glow_op_anim.setDuration(12000)
        self._glow_op_anim.setLoopCount(-1)
        self._glow_op_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._glow_op_anim.setStartValue(0.72)
        self._glow_op_anim.setKeyValueAt(0.5, 0.86)
        self._glow_op_anim.setEndValue(0.72)
        self._glow_op_anim.start()

    def _animate_card(self, lifted: bool):
        if self._base_card_pos is None:
            self._base_card_pos = self._card.pos()

        self._hover_anim.stop()
        self._shadow_anim.stop()
        self._glow_hover_op_anim.stop()

        end_pos = self._base_card_pos + QPoint(0, -6) if lifted else self._base_card_pos
        self._hover_anim.setStartValue(self._card.pos())
        self._hover_anim.setEndValue(end_pos)
        self._hover_anim.start()

        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(56 if lifted else 42)
        self._shadow_anim.start()

        base = 0.78
        self._glow_hover_op_anim.setStartValue(self._glow_op.opacity())
        self._glow_hover_op_anim.setEndValue(min(1.0, base + (0.12 if lifted else -0.02)))
        self._glow_hover_op_anim.start()

    def eventFilter(self, obj, event):
        # Защита от ранних событий до полной инициализации
        login = getattr(self, "login", None)
        ed_user = getattr(login, "ed_user", None) if login else None
        ed_pass = getattr(login, "ed_pass", None) if login else None

        if obj is self._card:
            if event.type() == QEvent.Enter:
                self._animate_card(True)
            elif event.type() == QEvent.Leave:
                if not (ed_user and ed_user.hasFocus()) and not (ed_pass and ed_pass.hasFocus()):
                    self._animate_card(False)

        if obj in (ed_user, ed_pass):
            if event.type() == QEvent.FocusIn:
                self._animate_card(True)
            elif event.type() == QEvent.FocusOut:
                if not self._card.underMouse():
                    self._animate_card(False)

        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        card_geo = self._card.geometry()
        glow_w = self._glow.width()
        glow_h = self._glow.height()
        x = card_geo.center().x() - glow_w // 2
        y = card_geo.center().y() - glow_h // 2 - 20
        self._glow.move(x, y)
        self._glow.lower()

        self._base_card_pos = self._card.pos()

        # Старт дыхания glow после первого корректного позиционирования
        base_geo = self._glow.geometry()
        d = 26
        g0 = QRect(base_geo.x(), base_geo.y(), base_geo.width(), base_geo.height())
        g1 = QRect(base_geo.x() - d // 2, base_geo.y() - d // 2, base_geo.width() + d, base_geo.height() + d)

        if not getattr(self, "_glow_geo_started", False):
            self._glow_geo_anim.setStartValue(g0)
            self._glow_geo_anim.setKeyValueAt(0.5, g1)
            self._glow_geo_anim.setEndValue(g0)
            self._glow_geo_anim.start()
            self._glow_geo_started = True
