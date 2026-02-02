from __future__ import annotations

from typing import Optional, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QMessageBox
)


_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QTextEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus, QTextEdit:focus { border: 1px solid #7fb3ff; }
QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 600;
    min-height: 34px;
}
QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
QPushButton:pressed { background: #eef1f5; }
QLabel#title { font-weight: 700; color: #111111; }
"""


class GzCoachDialog(QDialog):
    def __init__(self, parent, title: str, data: Optional[Dict] = None):
        super().__init__(parent)
        self.setStyleSheet(_QSS)
        self.setWindowTitle(title)
        self.resize(520, 240)

        data = data or {}

        lbl = QLabel(title)
        lbl.setObjectName("title")

        self.ed_name = QLineEdit(data.get("full_name", "") or "")
        self.ed_name.setPlaceholderText("Фамилия Имя Отчество")

        self.ed_comment = QTextEdit(data.get("comment", "") or "")
        self.ed_comment.setPlaceholderText("Комментарий…")
        self.ed_comment.setFixedHeight(80)

        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(lbl)
        root.addWidget(QLabel("ФИО тренера *:"))
        root.addWidget(self.ed_name)
        root.addWidget(QLabel("Комментарий:"))
        root.addWidget(self.ed_comment)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(btn_ok)
        footer.addWidget(btn_cancel)
        root.addLayout(footer)

    def _on_ok(self):
        if not (self.ed_name.text() or "").strip():
            QMessageBox.warning(self, "Проверка", "ФИО тренера не может быть пустым.")
            return
        self.accept()

    def values(self) -> Dict:
        return {
            "full_name": (self.ed_name.text() or "").strip(),
            "comment": (self.ed_comment.toPlainText() or "").strip(),
        }
