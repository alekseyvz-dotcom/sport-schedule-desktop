# app/ui/rules_window.py
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from app.ui.fit_screen import fit_dialog_to_screen


class RulesWindow(QDialog):
    """Отдельное окно для таблицы правил: занимает почти весь экран и прокручивается."""

    def __init__(self, parent: QWidget, title: str, content: QWidget):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle(title)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)
        root.addWidget(content, 1)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(btn_close)
        root.addLayout(footer)

        fit_dialog_to_screen(self, width=1100, height=680)
