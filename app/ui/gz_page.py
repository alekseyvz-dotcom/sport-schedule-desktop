from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QCheckBox, QHeaderView, QAbstractItemView, QDialog
)

from app.services.users_service import AuthUser
from app.services.gz_service import (
    GzGroup, list_groups, list_coaches, create_group, update_group, set_group_active
)
from app.ui.gz_group_dialog import GzGroupDialog


class GzPage(QWidget):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self._user = user

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск: тренер / год группы")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)

        top = QHBoxLayout()
        top.setContentsMargins(12, 12, 12, 8)
        top.setSpacing(10)
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["ID", "Тренер", "Год", "Примечание", "Активен", ""])
        self.tbl.setColumnHidden(5, True)  # тех. колонка если надо
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setShowGrid(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(self._on_edit)

        header = self.tbl.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self.setStyleSheet(
            """
            QWidget { background: #fbfbfc; }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QLineEdit:focus { border: 1px solid #7fb3ff; }
            QPushButton {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
            QPushButton:pressed { background: #eef1f5; }
            QCheckBox { padding: 0 6px; }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                selection-background-color: rgba(127,179,255,60);
                selection-color: #111111;
            }
            QHeaderView::section {
                background: #f6f7f9;
                color: #111111;
                padding: 8px 10px;
                border: none;
                border-bottom: 1px solid #e6e6e6;
                font-weight: 600;
            }
            QTableWidget::item { padding: 6px 10px; }
            """
        )

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        self.reload()

    def _selected_group(self) -> GzGroup | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def reload(self):
        try:
            groups = list_groups(search=self.ed_search.text(), include_inactive=self.cb_inactive.isChecked())
        except Exception as e:
            QMessageBox.critical(self, "Гос. задание", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for g in groups:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(g.id))
            it_id.setData(Qt.UserRole, g)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_active = QTableWidgetItem("Да" if g.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, QTableWidgetItem(g.coach_name))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(g.group_year)))
            self.tbl.setItem(r, 3, QTableWidgetItem(g.notes or ""))
            self.tbl.setItem(r, 4, it_active)

            if not g.is_active:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

    def _on_add(self):
        try:
            coaches = list_coaches(include_inactive=False)
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Не удалось загрузить тренеров:\n{e}")
            return

        if not coaches:
            QMessageBox.information(self, "Гос. задание", "Сначала добавьте тренеров (позже добавим кнопку прямо тут).")
            return

        dlg = GzGroupDialog(self, title="Создать группу ГЗ", coaches=coaches)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        try:
            new_id = create_group(coach_id=data["coach_id"], group_year=data["group_year"], notes=data["notes"])
        except Exception as e:
            QMessageBox.critical(self, "Создать группу", f"Ошибка:\n{e}")
            return

        self.reload()
        self._select_row_by_id(new_id)

    def _on_edit(self):
        g = self._selected_group()
        if not g:
            QMessageBox.information(self, "Редактировать", "Выберите группу.")
            return

        try:
            coaches = list_coaches(include_inactive=False)
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Не удалось загрузить тренеров:\n{e}")
            return

        dlg = GzGroupDialog(
            self,
            title=f"Редактировать группу ГЗ",
            coaches=coaches,
            data={"coach_id": g.coach_id, "group_year": g.group_year, "notes": g.notes},
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        try:
            update_group(g.id, coach_id=data["coach_id"], group_year=data["group_year"], notes=data["notes"])
        except Exception as e:
            QMessageBox.critical(self, "Редактировать группу", f"Ошибка:\n{e}")
            return

        self.reload()
        self._select_row_by_id(g.id)

    def _on_toggle_active(self):
        g = self._selected_group()
        if not g:
            QMessageBox.information(self, "Архив", "Выберите группу.")
            return

        new_state = not g.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(self, "Подтверждение", f"Вы действительно хотите {action} группу «{g.coach_name} {g.group_year}»?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_group_active(g.id, new_state)
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload()
        self._select_row_by_id(g.id)

    def _select_row_by_id(self, group_id: int) -> None:
        for r in range(self.tbl.rowCount()):
            it = self.tbl.item(r, 0)
            if it and it.text() == str(group_id):
                self.tbl.setCurrentCell(r, 0)
                self.tbl.scrollToItem(it)
                return
