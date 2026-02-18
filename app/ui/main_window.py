# app/ui/main_window.py
import os, tempfile, traceback
from PySide6.QtWidgets import QMainWindow, QTabWidget, QMessageBox
from datetime import date
from app.services.users_service import AuthUser
from app.ui.tenants_page import TenantsPage
from app.ui.orgs_venues_page import OrgsVenuesPage
from app.ui.schedule_page import SchedulePage
from app.ui.analytics_page import AnalyticsPage
from app.ui.welcome_login_page import WelcomeLoginPage
from app.ui.settings_page import SettingsPage
from app.ui.gz_page import GzPage
from app.ui.load_page import LoadPage


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
        try:
            self.user = user
            self.setWindowTitle(f"ИАС ФУТБОЛ — {user.username}")
    
            self.tabs = QTabWidget()
            self.page_schedule = None  # type: SchedulePage | None
    
            if self._can_tab("tab.tenants"):
                self.tabs.addTab(TenantsPage(user), "Контрагенты")
            if self._can_tab("tab.gz"):
                self.tabs.addTab(GzPage(user), "Гос. задание")
            if self._can_tab("tab.orgs"):
                self.tabs.addTab(OrgsVenuesPage(user), "Учреждения и площадки")
    
            if self._can_tab("tab.schedule"):
                self.page_schedule = SchedulePage(user)
                self.tabs.addTab(self.page_schedule, "Расписание")
    
            if self._can_tab("tab.load"):
                self.tabs.addTab(
                    LoadPage(user, open_schedule_cb=self._open_schedule_from_load),
                    "Загрузка"
                )
    
            if self._can_tab("tab.analytics"):
                self.tabs.addTab(AnalyticsPage(user), "Аналитика")
            if self._can_tab("tab.settings"):
                self.tabs.addTab(SettingsPage(user), "Настройки")
    
            self.setCentralWidget(self.tabs)
    
        except Exception as e:
            path = os.path.join(tempfile.gettempdir(), "app_login_error.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n=== on_logged_in ERROR ===\n")
                f.write(traceback.format_exc())
            QMessageBox.critical(
                self,
                "Ошибка после входа",
                f"{type(e).__name__}: {e}\n\nЛог: {path}",
            )

    def _can_tab(self, code: str) -> bool:
        if not self.user:
            return False
        if (self.user.role_code or "").lower() == "admin":
            return True
        return code in (self.user.permissions or set())

    def _open_schedule_from_load(self, org_id: int, day: date) -> None:
        if not getattr(self, "page_schedule", None):
            QMessageBox.information(self, "Расписание", "Вкладка 'Расписание' недоступна по правам.")
            return
    
        # переключаемся на вкладку расписания
        idx = self.tabs.indexOf(self.page_schedule)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
    
        # выставляем учреждение и дату
        i_org = self.page_schedule.cmb_org.findData(int(org_id))
        if i_org >= 0:
            self.page_schedule.cmb_org.setCurrentIndex(i_org)
    
        self.page_schedule.dt_day.setDate(day)
        self.page_schedule._set_mode("grid")
        self.page_schedule.reload()
