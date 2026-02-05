# app/ui/main_window.py
from PySide6.QtWidgets import QMainWindow, QTabWidget, QApplication
from app.services.users_service import AuthUser
from app.ui.tenants_page import TenantsPage
from app.ui.orgs_venues_page import OrgsVenuesPage
from app.ui.schedule_page import SchedulePage
from app.ui.analytics_page import AnalyticsPage
from app.ui.welcome_login_page import WelcomeLoginPage
from app.ui.settings_page import SettingsPage
from app.ui.gz_page import GzPage
from app.ui.theme import DARK_APP_QSS


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.user: AuthUser | None = None
        self.setWindowTitle("ИАС ФУТБОЛ")
        self.statusBar().showMessage("Разработал Алексей Зезюкин")

        self.welcome = WelcomeLoginPage()
        self.welcome.logged_in.connect(self.on_logged_in)
        self.setCentralWidget(self.welcome)

    def on_logged_in(self, user: AuthUser):
        self.user = user
        self.setWindowTitle(f"ИАС ФУТБОЛ — {user.username}")

        # Применяем общую тёмную тему на всё приложение
        QApplication.instance().setStyleSheet(DARK_APP_QSS)

        tabs = QTabWidget()

        if self._can_tab("tab.tenants"):
            tabs.addTab(TenantsPage(user), "Контрагенты")
        if self._can_tab("tab.gz"):
            tabs.addTab(GzPage(user), "Гос. задание")
        if self._can_tab("tab.orgs"):
            tabs.addTab(OrgsVenuesPage(user), "Учреждения и площадки")
        if self._can_tab("tab.schedule"):
            tabs.addTab(SchedulePage(user), "Расписание")
        if self._can_tab("tab.analytics"):
            tabs.addTab(AnalyticsPage(user), "Аналитика")
        if self._can_tab("tab.settings"):
            tabs.addTab(SettingsPage(user), "Настройки")

        self.setCentralWidget(tabs)

    def _can_tab(self, code: str) -> bool:
        if not self.user:
            return False
        if (self.user.role_code or "").lower() == "admin":
            return True
        return code in (self.user.permissions or set())
