import sys
from PySide6.QtWidgets import QApplication

from app.db import init_pool
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

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
