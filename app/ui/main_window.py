# app/ui/main_window.py
from PySide6.QtWidgets import QMainWindow, QTabWidget
from app.services.users_service import AuthUser
from app.ui.tenants_page import TenantsPage
from app.ui.orgs_venues_page import OrgsVenuesPage
from app.ui.schedule_page import SchedulePage
from app.ui.org_usage_page import OrgUsagePage
from app.ui.welcome_login_page import WelcomeLoginPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.user: AuthUser | None = None
        self.setWindowTitle("Sport Schedule")

        self.welcome = WelcomeLoginPage()
        self.welcome.logged_in.connect(self.on_logged_in)
        self.setCentralWidget(self.welcome)

    def on_logged_in(self, user: AuthUser):
        self.user = user
        self.setWindowTitle(f"Sport Schedule — {user.username}")

        tabs = QTabWidget()
        tabs.addTab(TenantsPage(user), "Контрагенты")
        tabs.addTab(OrgsVenuesPage(), "Учреждения и площадки")
        tabs.addTab(SchedulePage(), "Расписание")
        tabs.addTab(OrgUsagePage(self), "Загрузка учреждений")

        self.setCentralWidget(tabs)
