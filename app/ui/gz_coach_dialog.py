from __future__ import annotations

from typing import Optional, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
)


class GzCoachDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        *,
        data: Optional[Dict] = None,
        orgs: List[Dict],                # [{id, name}]
        selected_org_ids: Optional[List[int]] = None,
    ):
        super().__init__(parent)

        self.setObjectName("dialog")
        self.setWindowTitle(title)
        self.resize(520, 420)

        data = data or {}
        selected = {int(x) for x in (selected_org_ids or [])}

        lbl = QLabel(title)
        lbl.setObjectName("dialogTitle")  # можно добавить стиль в theme.py при желании

        self.ed_name = QLineEdit(data.get("full_name", "") or "")
        self.ed_name.setPlaceholderText("Фамилия Имя Отчество")

        self.ed_comment = QTextEdit(data.get("comment", "") or "")
        self.ed_comment.setPlaceholderText("Комментарий…")
        self.ed_comment.setFixedHeight(90)

        self.lst_orgs = QListWidget()
        self.lst_orgs.setMinimumHeight(170)
        self.lst_orgs.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        for o in orgs:
            it = QListWidgetItem(str(o["name"]))
            it.setData(Qt.ItemDataRole.UserRole, int(o["id"]))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            it.setCheckState(Qt.CheckState.Checked if int(o["id"]) in selected else Qt.CheckState.Unchecked)
            self.lst_orgs.addItem(it)

        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_ok.setObjectName("primary")  # будет “primary” из theme.py
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(lbl)

        root.addWidget(QLabel("ФИО тренера *:"))
        root.addWidget(self.ed_name)

        root.addWidget(QLabel("Объекты (учреждения) *:"))
        root.addWidget(self.lst_orgs, 1)

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
        if not self._selected_org_ids():
            QMessageBox.warning(self, "Проверка", "Нужно выбрать хотя бы один объект (учреждение).")
            return
        self.accept()

    def _selected_org_ids(self) -> List[int]:
        out: List[int] = []
        for i in range(self.lst_orgs.count()):
            it = self.lst_orgs.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                out.append(int(it.data(Qt.ItemDataRole.UserRole)))
        return out

    def values(self) -> Dict:
        return {
            "full_name": (self.ed_name.text() or "").strip(),
            "comment": (self.ed_comment.toPlainText() or "").strip(),
            "org_ids": self._selected_org_ids(),
        }
