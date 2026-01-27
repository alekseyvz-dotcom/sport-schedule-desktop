from __future__ import annotations

from typing import Optional, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox, QTextEdit
)

class TenantDialog(QDialog):
    def __init__(self, parent=None, title: str = "Арендатор", data: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._data_in = data or {}

        self.ed_name = QLineEdit(self._data_in.get("name", ""))
        self.ed_inn = QLineEdit(self._data_in.get("inn", "") or "")
        self.ed_phone = QLineEdit(self._data_in.get("phone", "") or "")
        self.ed_email = QLineEdit(self._data_in.get("email", "") or "")
        self.ed_comment = QTextEdit(self._data_in.get("comment", "") or "")

        form = QFormLayout()
        form.addRow("Название *:", self.ed_name)
        form.addRow("ИНН:", self.ed_inn)
        form.addRow("Телефон:", self.ed_phone)
        form.addRow("Email:", self.ed_email)
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
            "inn": self.ed_inn.text().strip(),
            "phone": self.ed_phone.text().strip(),
            "email": self.ed_email.text().strip(),
            "comment": self.ed_comment.toPlainText().strip(),
        }
