from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTextEdit, QMessageBox
)

from app.services.gz_service import GzCoach
from app.ui.gz_rules_widget import GzRulesWidget


_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QComboBox, QTextEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 6px 10px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 1px solid #7fb3ff; }
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


class GzGroupDialog(QDialog):
    def __init__(self, parent, title: str, coaches: List[GzCoach], data: Optional[Dict] = None):
        super().__init__(parent)
        self.setStyleSheet(_QSS)
        self.setWindowTitle(title)
        self.resize(560, 260)

        lbl = QLabel(title)
        lbl.setObjectName("title")

        self.cmb_coach = QComboBox()
        for c in coaches:
            self.cmb_coach.addItem(c.full_name, c.id)

        self.ed_year = QLineEdit()
        self.ed_year.setPlaceholderText("Например: 2012")

        self.ed_notes = QTextEdit()
        self.ed_notes.setPlaceholderText("Примечание…")
        self.ed_notes.setFixedHeight(90)

        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(lbl)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Тренер:"), 0)
        r1.addWidget(self.cmb_coach, 1)
        root.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Год группы:"), 0)
        r2.addWidget(self.ed_year, 1)
        root.addLayout(r2)

        root.addWidget(QLabel("Примечание:"))
        root.addWidget(self.ed_notes)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(btn_ok)
        footer.addWidget(btn_cancel)
        root.addLayout(footer)

        if data:
            coach_id = data.get("coach_id")
            if coach_id is not None:
                idx = self.cmb_coach.findData(int(coach_id))
                if idx >= 0:
                    self.cmb_coach.setCurrentIndex(idx)
            self.ed_year.setText(str(data.get("group_year") or ""))
            self.ed_notes.setPlainText(str(data.get("notes") or ""))

    def _on_ok(self):
        try:
            int((self.ed_year.text() or "").strip())
        except Exception:
            QMessageBox.warning(self, "Проверка", "Год группы должен быть числом.")
            return
        self.accept()

    def values(self) -> Dict:
        return {
            "coach_id": int(self.cmb_coach.currentData()),
            "group_year": int((self.ed_year.text() or "").strip()),
            "notes": (self.ed_notes.toPlainText() or "").strip(),
        }
