from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from app.services.users_service import AuthUser
from app.ui.org_usage_page import OrgUsagePage
from app.ui.tenant_usage_page import TenantUsagePage


class AnalyticsPage(QWidget):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)

        # Важно для общего фона страниц (theme.py: QWidget#page {...})
        self.setObjectName("page")

        tabs = QTabWidget(self)
        tabs.setObjectName("analyticsTabs")  # необязательно, но удобно если захочешь точечно стилизовать
        tabs.addTab(OrgUsagePage(self), "Учреждения")
        tabs.addTab(TenantUsagePage(user, self), "Арендаторы")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addWidget(tabs, 1)
