from PySide6.QtWidgets import QMainWindow, QTabWidget
from app.services.users_service import AuthUser
from app.ui.tenants_page import TenantsPage
from app.ui.orgs_venues_page import OrgsVenuesPage
from app.ui.schedule_page import SchedulePage
from app.ui.analytics_page import AnalyticsPage
from app.ui.welcome_login_page import WelcomeLoginPage
from app.ui.settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.user: AuthUser | None = None
        self.setWindowTitle("ИАС ФУТБОЛ")

        self.welcome = WelcomeLoginPage()
        self.welcome.logged_in.connect(self.on_logged_in)
        self.setCentralWidget(self.welcome)

    def on_logged_in(self, user: AuthUser):
        self.user = user
        self.setWindowTitle(f"ИАС ФУТБОЛ — {user.username}")

        tabs = QTabWidget()
        tabs.addTab(TenantsPage(user), "Контрагенты")
        tabs.addTab(OrgsVenuesPage(), "Учреждения и площадки")
        tabs.addTab(SchedulePage(user), "Расписание")
        tabs.addTab(AnalyticsPage(user), "Аналитика")
        if user.role_code.lower() == "admin":
            tabs.addTab(SettingsPage(user), "Настройки")

        self.setCentralWidget(tabs)
