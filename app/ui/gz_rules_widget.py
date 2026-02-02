from __future__ import annotations

from typing import Optional, Dict, List
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox,
    QTextEdit, QMessageBox, QLabel, QGroupBox, QScrollArea, QSizePolicy, QComboBox
)

from app.services.gz_service import GzCoach
from app.ui.gz_rules_widget import GzRulesWidget


_DIALOG_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QTextEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #7fb3ff;
}
QTextEdit#smallText { min-height: 34px; max-height: 54px; }
QGroupBox {
    border: 1px solid #e6e6e6;
    border-radius: 12px;
    margin-top: 10px;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #111111;
    font-weight: 700;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
    min-height: 34px;
}
QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
QPushButton:pressed { background: #eef1f5; }
QScrollArea { border: none; background: transparent; }
"""


class GzGroupDialog(QDialog):
    def __init__(
        self,
        parent=None,
        title: str = "Гос. задание",
        data: Optional[Dict] = None,
        *,
        coaches: List[GzCoach],
        is_admin: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_QSS)

        self._data_in = data or {}
        self._is_admin = bool(is_admin)

        self._group_id: Optional[int] = self._data_in.get("id")

        self.resize(980, 620)
        self.setSizeGripEnabled(True)

        # --- fields
        self.cmb_coach = QComboBox()
        for c in coaches:
            self.cmb_coach.addItem(c.full_name, c.id)

        self.ed_year = QLineEdit(str(self._data_in.get("group_year") or ""))
        self.ed_notes = QTextEdit(self._data_in.get("notes", "") or "")
        self.ed_notes.setObjectName("smallText")
        self.ed_notes.setFixedHeight(48)

        # preselect coach
        coach_id = self._data_in.get("coach_id")
        if coach_id is not None:
            idx = self.cmb_coach.findData(int(coach_id))
            if idx >= 0:
                self.cmb_coach.setCurrentIndex(idx)

        # --- groups
        gb_main = QGroupBox("Основное")
        fm = QFormLayout(gb_main)
        fm.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        fm.setHorizontalSpacing(12)
        fm.setVerticalSpacing(8)
        fm.addRow("Тренер *:", self.cmb_coach)
        fm.addRow("Год группы *:", self.ed_year)

        gb_notes = QGroupBox("Примечание")
        fm2 = QFormLayout(gb_notes)
        fm2.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        fm2.addRow("Комментарий:", self.ed_notes)
        gb_notes.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        gb_rules = QGroupBox("Правила расписания (ГЗ)")
        rules_layout = QVBoxLayout(gb_rules)
        rules_layout.setContentsMargins(12, 16, 12, 12)

        self.rules_widget = GzRulesWidget(self, gz_group_id=self._group_id, is_admin=self._is_admin)
        self.rules_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.rules_widget.setMinimumHeight(260)

        scroll = QScrollArea(gb_rules)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.rules_widget)
        rules_layout.addWidget(scroll, 1)
        gb_rules.setMinimumHeight(300)

        # --- layout
        cols = QHBoxLayout()
        cols.setContentsMargins(12, 12, 12, 6)
        cols.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(gb_main)
        left.addWidget(gb_notes)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(gb_rules, 1)

        cols.addLayout(left, 1)
        cols.addLayout(right, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 10)
        root.setSpacing(8)
        root.addLayout(cols, 1)
        root.addWidget(buttons, 0)

    def _on_accept(self):
        if self.cmb_coach.currentData() is None:
            QMessageBox.warning(self, "Гос. задание", "Выберите тренера.")
            return

        try:
            year = int((self.ed_year.text() or "").strip())
        except Exception:
            QMessageBox.warning(self, "Гос. задание", "Год группы должен быть числом.")
            return

        if year < 1900 or year > 2100:
            QMessageBox.warning(self, "Гос. задание", "Проверьте год группы.")
            return

        self.accept()

    def values(self) -> Dict:
        return {
            "coach_id": int(self.cmb_coach.currentData()),
            "group_year": int((self.ed_year.text() or "").strip()),
            "notes": (self.ed_notes.toPlainText() or "").strip(),
        }

    def rules_payload(self) -> list[dict]:
        return self.rules_widget.rules_payload()
