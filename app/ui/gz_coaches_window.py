from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QCheckBox, QAbstractItemView, QHeaderView
)

from app.services.gz_service import (
    GzCoach, list_coaches, create_coach, update_coach, set_coach_active
)
from app.ui.gz_coach_dialog import GzCoachDialog


class GzCoachesWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Тренеры (ГЗ)")
        self.resize(760, 520)

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск тренера…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")
        self.btn_close = QPushButton("Закрыть")

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)
        self.btn_close.clicked.connect(self.accept)

        top = QHBoxLayout()
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["ID", "ФИО", "Комментарий", "Активен"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(self._on_edit)

        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.btn_close)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)
        root.addLayout(bottom)

        self.reload()

    def _selected(self) -> GzCoach | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def reload(self):
        try:
            rows = list_coaches(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for c in rows:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(c.id))
            it_id.setData(Qt.ItemDataRole.UserRole, c)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_active = QTableWidgetItem("Да" if c.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, QTableWidgetItem(c.full_name))
            self.tbl.setItem(r, 2, QTableWidgetItem(c.comment or ""))
            self.tbl.setItem(r, 3, it_active)

            if not c.is_active:
                for col in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, col)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

    def _on_add(self):
        dlg = GzCoachDialog(self, "Создать тренера")
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            create_coach(v["full_name"], v.get("comment", ""))
        except Exception as e:
            QMessageBox.critical(self, "Создать тренера", str(e))
            return
        self.reload()

    def _on_edit(self):
        c = self._selected()
        if not c:
            QMessageBox.information(self, "Тренеры", "Выберите тренера.")
            return

        dlg = GzCoachDialog(self, "Редактировать тренера", data={"full_name": c.full_name, "comment": c.comment})
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            update_coach(c.id, v["full_name"], v.get("comment", ""))
        except Exception as e:
            QMessageBox.critical(self, "Редактировать тренера", str(e))
            return
        self.reload()

    def _on_toggle_active(self):
        c = self._selected()
        if not c:
            QMessageBox.information(self, "Тренеры", "Выберите тренера.")
            return

        new_state = not c.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(self, "Подтверждение", f"Вы действительно хотите {action} «{c.full_name}»?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_coach_active(c.id, new_state)
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", str(e))
            return
        self.reload()
