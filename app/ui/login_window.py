from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QHBoxLayout
)

from app.services.users_service import authenticate, AuthUser

class LoginWindow(QWidget):
    logged_in = Signal(object)  # AuthUser

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Вход — Sport Schedule")
        self.setFixedWidth(420)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #b00020;")

        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("Логин")

        self.ed_pass = QLineEdit()
        self.ed_pass.setPlaceholderText("Пароль")
        self.ed_pass.setEchoMode(QLineEdit.Password)

        self.btn_login = QPushButton("Войти")
        self.btn_login.clicked.connect(self._on_login)

        self.btn_exit = QPushButton("Выход")
        self.btn_exit.clicked.connect(self.close)

        form = QFormLayout()
        form.addRow("Логин:", self.ed_user)
        form.addRow("Пароль:", self.ed_pass)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btn_login)
        btns.addWidget(self.btn_exit)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.lbl_status)
        root.addLayout(btns)

        self.ed_user.returnPressed.connect(self._on_login)
        self.ed_pass.returnPressed.connect(self._on_login)

    def _on_login(self):
        self.lbl_status.setText("")
        u = self.ed_user.text()
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
