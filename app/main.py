import sys
# FORCE включить модуль в сборку PyInstaller
import app.services.tenants_service  # noqa: F401
import app.services.orgs_service     # noqa: F401

from PySide6.QtWidgets import QApplication

from app.db import init_pool
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow


CALENDAR_QSS = """
/* Чиним шапку/стрелки/выпадающее меню у календарей (QDateEdit calendarPopup) */
QCalendarWidget QWidget {
    background: #ffffff;
    color: #111111;
}

QCalendarWidget QToolButton {
    color: #111111;
    background: transparent;
    border: none;
    font-weight: 600;
    padding: 4px 8px;
}

QCalendarWidget QToolButton:hover {
    background: #f1f5f9;
    border-radius: 8px;
}

QCalendarWidget QMenu {
    background: #ffffff;
    color: #111111;
}

QCalendarWidget QSpinBox {
    background: #ffffff;
    color: #111111;
    border: 1px solid #e6e6e6;
    border-radius: 8px;
    padding: 2px 6px;
}

QCalendarWidget QAbstractItemView {
    selection-background-color: #7fb3ff;
    selection-color: #111111;
    background: #ffffff;
    color: #111111;
    outline: 0;
}
"""


def main():
    app = QApplication(sys.argv)

    # добавляем стиль календаря поверх любых уже заданных стилей
    app.setStyleSheet((app.styleSheet() or "") + "\n" + CALENDAR_QSS)

    # пул соединений (dsn берётся из settings.dat)
    init_pool(minconn=1, maxconn=5)

    login = LoginWindow()
    login.show()

    state = {"main": None}

    def on_logged_in(user):
        mw = MainWindow(user)
        state["main"] = mw
        mw.resize(1100, 700)
        mw.show()
        login.close()

    login.logged_in.connect(on_logged_in)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
