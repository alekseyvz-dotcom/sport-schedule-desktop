from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QTextEdit,
    QMessageBox,
    QGroupBox,
    QScrollArea,
    QCheckBox,
    QDateEdit,
)

from app.services.gz_service import GzCoach
from app.ui.gz_rules_widget import GzRulesWidget


_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QComboBox, QTextEdit, QDateEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 6px 10px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QDateEdit:focus { border: 1px solid #7fb3ff; }
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

QScrollArea { border: none; background: transparent; }
"""


class GzGroupDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        coaches: List[GzCoach],
        data: Optional[Dict] = None,
        *,
        is_admin: bool = False,
    ):
        super().__init__(parent)
        self.setStyleSheet(_QSS)
        self.setWindowTitle(title)
        self.resize(980, 620)

        self._is_admin = bool(is_admin)
        self._data_in = data or {}
        self._group_id: Optional[int] = self._data_in.get("id")

        lbl = QLabel(title)
        lbl.setObjectName("title")

        self.cmb_coach = QComboBox()
        for c in coaches:
            self.cmb_coach.addItem(c.full_name, c.id)

        self.ed_year = QLineEdit()
        self.ed_year.setPlaceholderText("Например: 2012 / ЭЯП (слабослышащие)")

        self.cb_free = QCheckBox("Безвозмездно")

        self.dt_from = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("dd.MM.yyyy")
        self.dt_from.setSpecialValueText("—")
        self.dt_from.setDate(date.today())
        self.dt_from.setMinimumDate(date(1900, 1, 1))
        self.dt_from.setEnabled(True)

        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("dd.MM.yyyy")
        self.dt_to.setSpecialValueText("—")
        self.dt_to.setDate(date.today())
        self.dt_to.setMinimumDate(date(1900, 1, 1))
        self.dt_to.setEnabled(True)

        self.ed_notes = QTextEdit()
        self.ed_notes.setPlaceholderText("Примечание…")
        self.ed_notes.setFixedHeight(70)

        # --- rules widget
        gb_rules = QGroupBox("Правила расписания (ГЗ)")
        rules_lay = QVBoxLayout(gb_rules)
        rules_lay.setContentsMargins(12, 16, 12, 12)

        self.rules_widget = GzRulesWidget(self, gz_group_id=self._group_id, is_admin=self._is_admin)

        scroll = QScrollArea(gb_rules)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.rules_widget)
        rules_lay.addWidget(scroll, 1)

        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        # --- layout
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(lbl)

        form = QGroupBox("Основное")
        form_lay = QVBoxLayout(form)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Тренер:"), 0)
        r1.addWidget(self.cmb_coach, 1)
        form_lay.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Группа:"), 0)
        r2.addWidget(self.ed_year, 1)
        form_lay.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(self.cb_free)
        r3.addStretch(1)
        form_lay.addLayout(r3)

        r4 = QHBoxLayout()
        r4.addWidget(QLabel("Период с:"), 0)
        r4.addWidget(self.dt_from, 0)
        r4.addSpacing(10)
        r4.addWidget(QLabel("по:"), 0)
        r4.addWidget(self.dt_to, 0)
        r4.addStretch(1)
        form_lay.addLayout(r4)

        form_lay.addWidget(QLabel("Примечание:"))
        form_lay.addWidget(self.ed_notes)

        root.addWidget(form)
        root.addWidget(gb_rules, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(btn_ok)
        footer.addWidget(btn_cancel)
        root.addLayout(footer)

        # --- initial values ---
        if data:
            coach_id = data.get("coach_id")
            if coach_id is not None:
                idx = self.cmb_coach.findData(int(coach_id))
                if idx >= 0:
                    self.cmb_coach.setCurrentIndex(idx)

            self.ed_year.setText(str(data.get("group_year") or ""))
            self.ed_notes.setPlainText(str(data.get("notes") or ""))

            self.cb_free.setChecked(bool(data.get("is_free", False)))

            pf = data.get("period_from")
            pt = data.get("period_to")
            if pf:
                self.dt_from.setDate(pf)
            if pt:
                self.dt_to.setDate(pt)

    def _on_ok(self):
        if not (self.ed_year.text() or "").strip():
            QMessageBox.warning(self, "Проверка", "Поле 'Группа' не может быть пустым.")
            return

        d0 = self.dt_from.date().toPython()
        d1 = self.dt_to.date().toPython()
        if d0 and d1 and d1 < d0:
            QMessageBox.warning(self, "Проверка", "Дата 'по' не может быть раньше даты 'с'.")
            return

        self.accept()

    def values(self) -> Dict:
        return {
            "coach_id": int(self.cmb_coach.currentData()),
            "group_year": (self.ed_year.text() or "").strip(),
            "is_free": bool(self.cb_free.isChecked()),
            "period_from": self.dt_from.date().toPython(),
            "period_to": self.dt_to.date().toPython(),
            "notes": (self.ed_notes.toPlainText() or "").strip(),
        }

    def rules_payload(self) -> list[dict]:
        return self.rules_widget.rules_payload()
