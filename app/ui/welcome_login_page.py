# app/ui/welcome_login_page.py
from PySide6.QtCore import (
    Qt, Signal, QEasingCurve, QPoint, QEvent,
    QPropertyAnimation, QParallelAnimationGroup, QSequentialAnimationGroup
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
        stop:0 rgba(99, 102, 241, 170),
        stop:0.35 rgba(99, 102, 241, 75),
        stop:1 rgba(99, 102, 241, 0)
    );
    border-radius: 260px;
}
QFrame#blobB {
    background: qradialgradient(cx:0.7, cy:0.6, radius:1.0,
        stop:0 rgba(34, 211, 238, 160),
        stop:0.35 rgba(34, 211, 238, 70),
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
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.10);   
    border-radius: 22px;
}

QFrame#cardInner {
    background: rgba(15, 23, 42, 0.35);
    border: none;                              
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

        # login — сразу, чтобы eventFilter не падал
        self.login = LoginWindow()
        self.login.logged_in.connect(self.logged_in)

        # --- Blobs ---
        self._blob_a = QFrame(self)
        self._blob_a.setObjectName("blobA")
        self._blob_a.setFixedSize(520, 520)
        self._blob_a.lower()

        self._blob_b = QFrame(self)
        self._blob_b.setObjectName("blobB")
        self._blob_b.setFixedSize(600, 600)
        self._blob_b.lower()

        # дыхание (opacity)
        self._blob_a_op = QGraphicsOpacityEffect(self._blob_a)
        self._blob_a_op.setOpacity(0.95)
        self._blob_a.setGraphicsEffect(self._blob_a_op)

        self._blob_b_op = QGraphicsOpacityEffect(self._blob_b)
        self._blob_b_op.setOpacity(0.90)
        self._blob_b.setGraphicsEffect(self._blob_b_op)

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

        # --- Card hover/focus micro anim ---
        self._shadow = shadow
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(180)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._glow_hover_op_anim = QPropertyAnimation(self._glow_op, b"opacity", self)
        self._glow_hover_op_anim.setDuration(180)
        self._glow_hover_op_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._card.installEventFilter(self)
        self.login.ed_user.installEventFilter(self)
        self.login.ed_pass.installEventFilter(self)

        # bg motion will start after first resize (when we know size)
        self._bg_started = False

    # ---------- helpers ----------
    def _p(self, fx: float, fy: float, w: int, h: int, item_w: int, item_h: int) -> QPoint:
        # fx/fy can be <0 or >1 to go outside screen
        x = int(fx * w - item_w / 2)
        y = int(fy * h - item_h / 2)
        return QPoint(x, y)

    def _make_pingpong_pos_anim(
        self,
        widget: QFrame,
        duration_ms: int,
        points: list[QPoint],
        easing: QEasingCurve.Type = QEasingCurve.InOutSine,
    ) -> QSequentialAnimationGroup:
        """
        Smooth infinite loop without teleport:
        forward(points[0]->...->points[-1]) then backward(points[-1]->...->points[0]).
        """
        if len(points) < 2:
            raise ValueError("Need at least 2 points for animation")

        forward = QPropertyAnimation(widget, b"pos", self)
        forward.setDuration(duration_ms)
        forward.setEasingCurve(easing)
        forward.setStartValue(points[0])
        n = len(points)
        for i in range(1, n - 1):
            forward.setKeyValueAt(i / (n - 1), points[i])
        forward.setEndValue(points[-1])

        backward = QPropertyAnimation(widget, b"pos", self)
        backward.setDuration(duration_ms)
        backward.setEasingCurve(easing)
        backward.setStartValue(points[-1])
        rev = list(reversed(points))
        n2 = len(rev)
        for i in range(1, n2 - 1):
            backward.setKeyValueAt(i / (n2 - 1), rev[i])
        backward.setEndValue(rev[-1])

        seq = QSequentialAnimationGroup(self)
        seq.setLoopCount(-1)
        seq.addAnimation(forward)
        seq.addAnimation(backward)
        return seq

    def _start_background_float(self):
        w = max(1, self.width())
        h = max(1, self.height())

        a_w, a_h = self._blob_a.width(), self._blob_a.height()
        b_w, b_h = self._blob_b.width(), self._blob_b.height()

        # Точки траектории (край-край, с выходом за экран)
        a_points = [
            self._p(-0.15, 0.12, w, h, a_w, a_h),
            self._p(0.18, 0.35, w, h, a_w, a_h),
            self._p(0.62, 0.10, w, h, a_w, a_h),
            self._p(1.15, 0.52, w, h, a_w, a_h),
        ]
        b_points = [
            self._p(1.12, 0.78, w, h, b_w, b_h),
            self._p(0.78, 0.55, w, h, b_w, b_h),
            self._p(0.30, 0.92, w, h, b_w, b_h),
            self._p(-0.20, 0.30, w, h, b_w, b_h),
        ]

        # Ставим начальные позиции
        self._blob_a.move(a_points[0])
        self._blob_b.move(b_points[0])

        # Ping-pong pos (без перескока) + дыхание opacity
        self._blob_a_pos_seq = self._make_pingpong_pos_anim(self._blob_a, 26000, a_points)
        self._blob_b_pos_seq = self._make_pingpong_pos_anim(self._blob_b, 32000, b_points)

        self._blob_a_op_anim = QPropertyAnimation(self._blob_a_op, b"opacity", self)
        self._blob_a_op_anim.setDuration(9000)
        self._blob_a_op_anim.setLoopCount(-1)
        self._blob_a_op_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_a_op_anim.setStartValue(0.78)
        self._blob_a_op_anim.setKeyValueAt(0.5, 0.98)
        self._blob_a_op_anim.setEndValue(0.78)

        self._blob_b_op_anim = QPropertyAnimation(self._blob_b_op, b"opacity", self)
        self._blob_b_op_anim.setDuration(11000)
        self._blob_b_op_anim.setLoopCount(-1)
        self._blob_b_op_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._blob_b_op_anim.setStartValue(0.70)
        self._blob_b_op_anim.setKeyValueAt(0.5, 0.92)
        self._blob_b_op_anim.setEndValue(0.70)

        self._blob_a_group = QParallelAnimationGroup(self)
        self._blob_a_group.addAnimation(self._blob_a_pos_seq)
        self._blob_a_group.addAnimation(self._blob_a_op_anim)
        self._blob_a_group.start()

        self._blob_b_group = QParallelAnimationGroup(self)
        self._blob_b_group.addAnimation(self._blob_b_pos_seq)
        self._blob_b_group.addAnimation(self._blob_b_op_anim)
        self._blob_b_group.start()

        self._bg_started = True

    # ---------- card micro animation ----------
    def _animate_card(self, lifted: bool):
        self._shadow_anim.stop()
        self._glow_hover_op_anim.stop()
    
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(56 if lifted else 42)
        self._shadow_anim.start()
    
        base = 0.78
        self._glow_hover_op_anim.setStartValue(self._glow_op.opacity())
        self._glow_hover_op_anim.setEndValue(min(1.0, base + (0.12 if lifted else -0.02)))
        self._glow_hover_op_anim.start()


    def eventFilter(self, obj, event):
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
    
        self._reposition_glow()
    
        if not self._bg_started and self.width() > 10 and self.height() > 10:
            self._start_background_float()

    def _reposition_glow(self):
        card_geo = self._card.geometry()
        glow_w = self._glow.width()
        glow_h = self._glow.height()
        x = card_geo.center().x() - glow_w // 2
        y = card_geo.center().y() - glow_h // 2 - 20
        self._glow.move(x, y)
        self._glow.lower()

