from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

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
    QFrame,
)

from app.services.gz_service import GzCoach
from app.ui.gz_rules_widget import GzRulesWidget

from PySide6.QtGui import QColor, QPalette


def _style_calendar_widget(date_edit: QDateEdit) -> None:
    cal = date_edit.calendarWidget()
    if cal is None:
        return
    from PySide6.QtWidgets import QWidget

    dark_bg = QColor("#0f172a")
    darker_bg = QColor("#0b1220")
    text_color = QColor(226, 232, 240)
    accent = QColor(99, 102, 241)
    dim_text = QColor(226, 232, 240, 120)

    pal = cal.palette()
    pal.setColor(QPalette.ColorRole.Window, dark_bg)
    pal.setColor(QPalette.ColorRole.Base, darker_bg)
    pal.setColor(QPalette.ColorRole.AlternateBase, dark_bg)
    pal.setColor(QPalette.ColorRole.WindowText, text_color)
    pal.setColor(QPalette.ColorRole.Text, text_color)
    pal.setColor(QPalette.ColorRole.ButtonText, text_color)
    pal.setColor(QPalette.ColorRole.ToolTipText, text_color)
    pal.setColor(QPalette.ColorRole.Button, dark_bg)
    pal.setColor(QPalette.ColorRole.Highlight, accent)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, dim_text)
    pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, dim_text)

    cal.setPalette(pal)
    for child in cal.findChildren(QWidget):
        child.setPalette(pal)
        child.setAutoFillBackground(True)
    cal.setAutoFillBackground(True)

    cal.setStyleSheet("""
        QCalendarWidget { background: #0b1220; border: 1px solid rgba(255,255,255,0.14); border-radius: 8px; }
        QCalendarWidget QWidget { background: #0f172a; color: rgba(226,232,240,0.90); }
        QCalendarWidget QToolButton { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); border-radius: 8px; padding: 4px 8px; color: rgba(255,255,255,0.90); font-weight: 700; }
        QCalendarWidget QToolButton:hover { background: rgba(255,255,255,0.10); border-color: rgba(255,255,255,0.22); }
        QCalendarWidget QToolButton::menu-indicator { image: none; width: 0px; }
        QCalendarWidget QSpinBox { background: #0b1220; color: rgba(255,255,255,0.92); border: 1px solid rgba(255,255,255,0.14); border-radius: 6px; padding: 2px 6px; }
        QCalendarWidget QMenu { background: #0b1220; color: rgba(255,255,255,0.90); border: 1px solid rgba(255,255,255,0.14); }
        QCalendarWidget QMenu::item:selected { background: rgba(99,102,241,0.35); }
        QCalendarWidget QAbstractItemView { background: #0b1220; color: rgba(255,255,255,0.88); selection-background-color: rgba(99,102,241,0.45); selection-color: rgba(255,255,255,0.95); alternate-background-color: #0b1220; outline: 0; border: none; }
        QCalendarWidget QAbstractItemView::item { padding: 4px; }
        QCalendarWidget QAbstractItemView::item:hover { background: rgba(255,255,255,0.08); }
        QCalendarWidget QAbstractItemView::item:selected { background: rgba(99,102,241,0.45); }
        QCalendarWidget QHeaderView::section { background: #0f172a; color: rgba(226,232,240,0.70); border: none; padding: 4px; font-weight: 700; }
    """)

class GzGroupDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        coaches: List[GzCoach],
        data: Optional[Dict] = None,
        *,
        is_admin: bool = False,
        user_id: int,
        role_code: str,
    ):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle(title)
        self.resize(980, 620)

        self._user_id = int(user_id)
        self._role_code = str(role_code or "")

        self._is_admin = bool(is_admin)
        self._data_in = data or {}
        self._group_id: Optional[int] = self._data_in.get("id")

        lbl = QLabel(title)
        lbl.setObjectName("title")  # можно потом добавить стиль в theme.py

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

        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("dd.MM.yyyy")
        self.dt_to.setSpecialValueText("—")
        self.dt_to.setDate(date.today())
        self.dt_to.setMinimumDate(date(1900, 1, 1))

        _style_calendar_widget(self.dt_from)
        _style_calendar_widget(self.dt_to)

        self.ed_notes = QTextEdit()
        self.ed_notes.setPlaceholderText("Примечание…")
        self.ed_notes.setFixedHeight(70)

        # --- initial values (важно сделать ДО rules_widget, чтобы передать период)
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

        # --- rules widget
        gb_rules = QGroupBox("Правила расписания (ГЗ)")
        rules_lay = QVBoxLayout(gb_rules)
        rules_lay.setContentsMargins(12, 16, 12, 12)
        rules_lay.setSpacing(10)

        self.rules_widget = GzRulesWidget(
            self,
            gz_group_id=self._group_id,
            is_admin=self._is_admin,
            group_period_from=self.dt_from.date().toPython(),
            group_period_to=self.dt_to.date().toPython(),
            user_id=self._user_id,
            role_code=self._role_code,
        )

        self.dt_from.dateChanged.connect(self._sync_rules_period)
        self.dt_to.dateChanged.connect(self._sync_rules_period)

        scroll = QScrollArea(gb_rules)
        scroll.setObjectName("rulesScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.rules_widget)
        rules_lay.addWidget(scroll, 1)

        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        # --- layout
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(lbl)

        form = QGroupBox("Основное")
        form_lay = QVBoxLayout(form)
        form_lay.setContentsMargins(12, 16, 12, 12)
        form_lay.setSpacing(10)

        r1 = QHBoxLayout()
        r1.setSpacing(10)
        r1.addWidget(QLabel("Тренер:"), 0)
        r1.addWidget(self.cmb_coach, 1)
        form_lay.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(10)
        r2.addWidget(QLabel("Группа:"), 0)
        r2.addWidget(self.ed_year, 1)
        form_lay.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(self.cb_free)
        r3.addStretch(1)
        form_lay.addLayout(r3)

        r4 = QHBoxLayout()
        r4.setSpacing(10)
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

    def _sync_rules_period(self, *_):
        if hasattr(self, "rules_widget") and self.rules_widget:
            self.rules_widget.set_group_period(
                self.dt_from.date().toPython(),
                self.dt_to.date().toPython(),
            )

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
