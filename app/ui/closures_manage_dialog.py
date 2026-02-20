# app/ui/closures_manage_dialog.py
from __future__ import annotations

from typing import Callable, Optional, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QHeaderView
)

from app.ui.period_edit_dialog import PeriodEditDialog


class ClosuresManageDialog(QDialog):
    """
    Универсальный менеджер закрытий.
    list_fn() -> list объектов с полями: id, date_from, date_to, reason, is_active
    create_fn(date_from, date_to, reason) -> id
    update_fn(closure_id, date_from, date_to, reason, is_active) -> None
    set_active_fn(closure_id, is_active) -> None
    """
    def __init__(
        self,
        parent=None,
        *,
        title: str,
        list_fn: Callable[..., list],
        create_fn: Callable[..., int],
        update_fn: Callable[..., None],
        set_active_fn: Callable[..., None],
    ):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle(title)

        self._list_fn = list_fn
        self._create_fn = create_fn
        self._update_fn = update_fn
        self._set_active_fn = set_active_fn

        self.cb_inactive = QCheckBox("Показывать неактивные")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_toggle = QPushButton("Активировать/деактивировать")

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_toggle.clicked.connect(self._toggle)

        top = QHBoxLayout()
        top.addWidget(self.cb_inactive, 1)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_toggle)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["ID", "С", "По", "Активно", "Причина"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(False)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.doubleClicked.connect(self._edit)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self.reload()

    def _selected(self) -> Optional[Any]:
        r = self.tbl.currentRow()
        if r < 0:
            return None
        it = self.tbl.item(r, 0)
        return it.data(Qt.UserRole) if it else None

    def reload(self):
        try:
            rows = self._list_fn(include_inactive=self.cb_inactive.isChecked())
        except Exception as e:
            QMessageBox.critical(self, "Закрытия", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for x in rows:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(x.id))
            it_id.setData(Qt.UserRole, x)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_from = QTableWidgetItem(x.date_from.strftime("%d.%m.%Y"))
            it_to = QTableWidgetItem(x.date_to.strftime("%d.%m.%Y"))
            it_act = QTableWidgetItem("Да" if x.is_active else "Нет")
            it_reason = QTableWidgetItem(x.reason or "")

            it_act.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, it_from)
            self.tbl.setItem(r, 2, it_to)
            self.tbl.setItem(r, 3, it_act)
            self.tbl.setItem(r, 4, it_reason)

            if not x.is_active:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

    def _add(self):
        dlg = PeriodEditDialog(self, title="Добавить закрытие", show_active=False)
        if dlg.exec() != PeriodEditDialog.Accepted:
            return
        v = dlg.values()
        try:
            self._create_fn(date_from=v.date_from, date_to=v.date_to, reason=v.reason)
        except Exception as e:
            QMessageBox.critical(self, "Закрытия", f"Ошибка сохранения:\n{e}")
            return
        self.reload()

    def _edit(self):
        x = self._selected()
        if not x:
            QMessageBox.information(self, "Закрытия", "Выберите запись.")
            return

        dlg = PeriodEditDialog(
            self,
            title="Редактировать закрытие",
            date_from=x.date_from,
            date_to=x.date_to,
            reason=x.reason or "",
            show_active=True,
            is_active=bool(x.is_active),
        )
        if dlg.exec() != PeriodEditDialog.Accepted:
            return
        v = dlg.values()
        try:
            self._update_fn(
                closure_id=x.id,
                date_from=v.date_from,
                date_to=v.date_to,
                reason=v.reason,
                is_active=v.is_active,
            )
        except Exception as e:
            QMessageBox.critical(self, "Закрытия", f"Ошибка сохранения:\n{e}")
            return
        self.reload()

    def _toggle(self):
        x = self._selected()
        if not x:
            QMessageBox.information(self, "Закрытия", "Выберите запись.")
            return

        new_state = not bool(x.is_active)
        action = "активировать" if new_state else "деактивировать"
        if (
            QMessageBox.question(self, "Подтверждение", f"Вы действительно хотите {action} запись?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            self._set_active_fn(closure_id=x.id, is_active=new_state)
        except Exception as e:
            QMessageBox.critical(self, "Закрытия", f"Ошибка:\n{e}")
            return
        self.reload()
