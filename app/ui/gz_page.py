# app/ui/gz_page.py
from __future__ import annotations

from datetime import timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QCheckBox,
    QHeaderView,
    QAbstractItemView,
    QDialog,
)

from app.services.users_service import AuthUser
from app.services.gz_service import (
    GzGroup,
    list_groups,
    list_coaches,
    create_group,
    update_group,
    set_group_active,
    list_accessible_org_ids,
)
from app.services.gz_rules_service import (
    create_rule,
    set_rule_active,
    generate_bookings_for_group,
)
from app.ui.gz_group_dialog import GzGroupDialog
from app.ui.gz_coaches_window import GzCoachesWindow


class GzPage(QWidget):
    TZ = timezone(timedelta(hours=3))

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

        self._user = user
        self._role = (getattr(user, "role_code", "") or "").lower()
        self._is_admin = self._role == "admin"
        self._can_edit = (self._role == "admin") or bool(
            list_accessible_org_ids(user_id=int(self._user.id), for_edit=True)
        )

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск: тренер / группа")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_coaches = QPushButton("Тренеры…")
        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")

        self.btn_coaches.clicked.connect(self._on_coaches)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)  # root уже даёт отступы
        top.setSpacing(10)
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_coaches)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setObjectName("gzGroupsTable")
        self.tbl.setHorizontalHeaderLabels(["ID", "Тренер", "Группа", "Примечание", "Активен"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setShowGrid(False)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(lambda *_: self._on_edit())

        header = self.tbl.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        # “карточка” под таблицу, чтобы фон был как у виджетов
        self.tbl_card = QWidget(self)
        self.tbl_card.setObjectName("detailsCard")
        card_lay = QVBoxLayout(self.tbl_card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        card_lay.setSpacing(0)
        card_lay.addWidget(self.tbl)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl_card, 1)

        self._apply_ui_access()
        self.reload()

    def _apply_ui_access(self):
        self.btn_add.setEnabled(self._can_edit)
        self.btn_edit.setEnabled(self._can_edit)
        self.btn_archive.setEnabled(self._can_edit)
        self.btn_coaches.setEnabled(self._can_edit)

    def _on_coaches(self):
        if not self._can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование тренеров.")
            return
        dlg = GzCoachesWindow(self._user, self)
        dlg.exec()
        self.reload()

    def _selected_group(self) -> GzGroup | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def reload(self):
        try:
            groups = list_groups(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
                user_id=self._user.id,
                role_code=self._user.role_code,
            )
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

    # остальная логика без изменений ...
