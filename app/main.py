import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sport Schedule")
        self.setCentralWidget(QLabel("OK: build from GitHub Actions works"))

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(900, 600)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
