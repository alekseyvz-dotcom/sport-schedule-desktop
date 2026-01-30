from __future__ import annotations

from datetime import time
from typing import Optional, Dict

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QDialogButtonBox,
    QCheckBox,
    QTimeEdit,
    QLabel,
    QMessageBox,
)


_DIALOG_QSS = """
QDialog { background: #fbfbfc; }
QLineEdit, QTextEdit, QTimeEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 22px;
}
QLineEdit:focus, QTextEdit:focus, QTimeEdit:focus { border: 1px solid #7fb3ff; }
QCheckBox { padding: 0 6px; }
QLabel#hint {
    color: #334155;
    padding: 0 6px;
}
"""


class OrgDialog(QDialog):
    """
    data (optional) supports:
      name, address, comment,
      work_start (datetime.time or "HH:MM"),
      work_end   (datetime.time or "HH:MM"),
      is_24h     (bool)
    """

    def __init__(self, parent=None, title: str = "Учреждение", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(_DIALOG_QSS)

        self._data_in = data or {}

        self.ed_name = QLineEdit(self._data_in.get("name", ""))
        self.ed_address = QLineEdit(self._data_in.get("address", "") or "")
        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        self.cb_24h = QCheckBox("Круглосуточно")
        self.cb_24h.setChecked(bool(self._data_in.get("is_24h") or False))
        self.cb_24h.stateChanged.connect(self._update_work_time_enabled)

        self.tm_start = QTimeEdit()
        self.tm_start.setDisplayFormat("HH:mm")
        self.tm_start.setTime(self._to_qtime(self._data_in.get("work_start"), fallback=time(8, 0)))

        self.tm_end = QTimeEdit()
        self.tm_end.setDisplayFormat("HH:mm")
        self.tm_end.setTime(self._to_qtime(self._data_in.get("work_end"), fallback=time(22, 0)))

        hint = QLabel("Режим работы влияет на аналитику и построение слотов расписания.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        form.addRow("Название *:", self.ed_name)
        form.addRow("Адрес:", self.ed_address)
        form.addRow("Комментарий:", self.ed_comment)
        form.addRow("Режим работы:", self.cb_24h)
        form.addRow("Начало:", self.tm_start)
        form.addRow("Окончание:", self.tm_end)
        form.addRow("", hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(form)
        root.addWidget(buttons)

        self._update_work_time_enabled()

    def _to_qtime(self, v, *, fallback: time) -> QTime:
        if isinstance(v, time):
            return QTime(v.hour, v.minute)
        if isinstance(v, str):
            try:
                hh, mm = v.strip().split(":")
                return QTime(int(hh), int(mm))
            except Exception:
                pass
        return QTime(fallback.hour, fallback.minute)

    def _update_work_time_enabled(self):
        enabled = not self.cb_24h.isChecked()
        self.tm_start.setEnabled(enabled)
        self.tm_end.setEnabled(enabled)

    def _on_accept(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Учреждение", "Название учреждения не может быть пустым.")
            return

        if not self.cb_24h.isChecked():
            s = self.tm_start.time()
            e = self.tm_end.time()
            # В текущей модели (и в чек-констрейнте БД) не поддерживаем смену через полночь
            if e <= s:
                QMessageBox.warning(self, "Режим работы", "Окончание должно быть позже начала (смены через полночь не поддерживаются).")
                return

        self.accept()

    def values(self) -> Dict:
        s = self.tm_start.time()
        e = self.tm_end.time()
        return {
            "name": self.ed_name.text().strip(),
            "address": self.ed_address.text().strip(),
            "comment": self.ed_comment.toPlainText().strip(),
            "is_24h": self.cb_24h.isChecked(),
            "work_start": time(s.hour(), s.minute()),
            "work_end": time(e.hour(), e.minute()),
        }
