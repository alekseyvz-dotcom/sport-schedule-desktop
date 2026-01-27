from PySide6.QtWidgets import QMainWindow, QTabWidget
from app.services.users_service import AuthUser
from app.ui.tenants_page import TenantsPage
from app.ui.orgs_venues_page import OrgsVenuesPage
from app.ui.schedule_page import SchedulePage

class MainWindow(QMainWindow):
    def __init__(self, user: AuthUser):
        super().__init__()
        self.setWindowTitle(f"Sport Schedule — {user.username}")

        tabs = QTabWidget()
        tabs.addTab(TenantsPage(), "Арендаторы")
        tabs.addTab(OrgsVenuesPage(), "Учреждения и площадки")
        tabs.addTab(SchedulePage(), "Расписание")

        self.setCentralWidget(tabs)
