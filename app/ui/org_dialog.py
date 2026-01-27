from __future__ import annotations

from typing import Optional, Dict
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox

class OrgDialog(QDialog):
    def __init__(self, parent=None, title: str = "Учреждение", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._data_in = data or {}

        self.ed_name = QLineEdit(self._data_in.get("name", ""))
        self.ed_address = QLineEdit(self._data_in.get("address", "") or "")
        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        form = QFormLayout()
        form.addRow("Название *:", self.ed_name)
        form.addRow("Адрес:", self.ed_address)
        form.addRow("Комментарий:", self.ed_comment)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def values(self) -> Dict:
        return {
            "name": self.ed_name.text().strip(),
            "address": self.ed_address.text().strip(),
            "comment": self.ed_comment.toPlainText().strip(),
        }
