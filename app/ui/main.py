import sys

import app.services.tenants_service  # noqa: F401
import app.services.orgs_service     # noqa: F401

from PySide6.QtWidgets import QApplication

from app.db import init_pool
from app.ui.main_window import MainWindow
from app.ui.theme import DARK_APP_QSS, apply_dark_palette


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
    app.setStyle("Fusion")

    # тёмная палитра — иначе на macOS остаётся светлая системная,
    # и полупрозрачные фоны из QSS дают мутно-серый цвет
    apply_dark_palette(app)

    # ОДИН раз задаём весь стиль приложению
    app.setStyleSheet(DARK_APP_QSS + "\n" + CALENDAR_QSS)

    init_pool(minconn=1, maxconn=5)

    mw = MainWindow()

    # вписываем главное окно в экран ноутбука
    from app.ui.fit_screen import fit_dialog_to_screen
    fit_dialog_to_screen(mw, width=1100, height=700)

    mw.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
