from PySide6.QtWidgets import QMainWindow, QLabel
from app.services.users_service import AuthUser

class MainWindow(QMainWindow):
    def __init__(self, user: AuthUser):
        super().__init__()
        self.setWindowTitle("Sport Schedule")
        self.setCentralWidget(QLabel(f"Вы вошли: {user.username} ({user.role_code})\nПрава: {len(user.permissions)}"))
