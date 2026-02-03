# app/ui/orgs_venues_page.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QLabel,
    QHeaderView,
    QAbstractItemView,
)

from app.services.users_service import AuthUser
from app.services.access_service import get_org_access

from app.services.orgs_service import (
    list_orgs,
    create_org,
    update_org,
    set_org_active,
    SportOrg,
)
from app.services.venues_service import (
    list_venues,
    create_venue,
    update_venue,
    set_venue_active,
    Venue,
)
from app.services.venue_units_manage_service import apply_units_scheme
from app.ui.org_dialog import OrgDialog
from app.ui.venue_dialog import VenueDialog


_TABLE_QSS = """
QTableWidget {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #d6e9ff;
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
QTableWidget::item {
    padding: 6px 10px;
    border: none;
}
QTableWidget::item:selected {
    background: #d6e9ff;
}
"""


_PAGE_QSS = """
QWidget {
    background: #fbfbfc;
}
QLineEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 10px;
}
QLineEdit:focus {
    border: 1px solid #7fb3ff;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 600;
}
QPushButton:hover {
    border: 1px solid #cfd6df;
    background: #f6f7f9;
}
QPushButton:pressed {
    background: #eef1f5;
}
QCheckBox {
    padding: 0 6px;
}
QLabel#sectionTitle {
    color: #111111;
    font-weight: 700;
    padding: 0 4px;
}
"""


class OrgsVenuesPage(QWidget):
    """
    Страница учреждений/площадок с учётом прав:
      - список учреждений фильтруется по can_view (через обновлённый list_orgs)
      - редактирование/архивирование доступно только при can_edit
      - создание учреждения — только admin (как в create_org)
      - для площадок UI ограничиваем по can_edit учреждения (сервис venues желательно тоже защитить)
    """

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.user = user
        self.setStyleSheet(_PAGE_QSS)

        # ---------- Orgs (left)
        self.lbl_orgs = QLabel("Учреждения")
        self.lbl_orgs.setObjectName("sectionTitle")

        self.ed_org_search = QLineEdit()
        self.ed_org_search.setPlaceholderText("Поиск учреждений: имя/адрес")
        self.ed_org_search.setClearButtonEnabled(True)
        self.ed_org_search.returnPressed.connect(self.reload_orgs)

        self.cb_org_inactive = QCheckBox("Архив")
        self.cb_org_inactive.stateChanged.connect(lambda *_: self.reload_orgs())

        self.btn_org_add = QPushButton("Создать")
        self.btn_org_edit = QPushButton("Редактировать")
        self.btn_org_archive = QPushButton("Архивировать/восстановить")

        self.btn_org_add.clicked.connect(self._org_add)
        self.btn_org_edit.clicked.connect(self._org_edit)
        self.btn_org_archive.clicked.connect(self._org_toggle)

        for b in (self.btn_org_add, self.btn_org_edit, self.btn_org_archive):
            b.setMinimumHeight(34)

        org_top = QHBoxLayout()
        org_top.setContentsMargins(12, 12, 12, 8)
        org_top.setSpacing(10)
        org_top.addWidget(self.lbl_orgs)
        org_top.addWidget(self.ed_org_search, 1)
        org_top.addWidget(self.cb_org_inactive)
        org_top.addWidget(self.btn_org_add)
        org_top.addWidget(self.btn_org_edit)
        org_top.addWidget(self.btn_org_archive)

        self.tbl_orgs = QTableWidget(0, 5)
        self.tbl_orgs.setHorizontalHeaderLabels(["ID", "Название", "Адрес", "Режим", "Активен"])
        self._style_table(self.tbl_orgs)

        self.tbl_orgs.itemSelectionChanged.connect(self._on_org_selected)
        self.tbl_orgs.doubleClicked.connect(self._org_edit)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        left.addLayout(org_top)
        left.addWidget(self.tbl_orgs, 1)

        # ---------- Venues (right)
        self.lbl_venues = QLabel("Площадки: (выберите учреждение слева)")
        self.lbl_venues.setObjectName("sectionTitle")

        self.cb_venue_inactive = QCheckBox("Архив")
        self.cb_venue_inactive.stateChanged.connect(lambda *_: self.reload_venues())

        self.btn_venue_add = QPushButton("Создать")
        self.btn_venue_edit = QPushButton("Редактировать")
        self.btn_venue_archive = QPushButton("Архивировать/восстановить")

        self.btn_venue_add.clicked.connect(self._venue_add)
        self.btn_venue_edit.clicked.connect(self._venue_edit)
        self.btn_venue_archive.clicked.connect(self._venue_toggle)

        for b in (self.btn_venue_add, self.btn_venue_edit, self.btn_venue_archive):
            b.setMinimumHeight(34)

        venue_top = QHBoxLayout()
        venue_top.setContentsMargins(12, 12, 12, 8)
        venue_top.setSpacing(10)
        venue_top.addWidget(self.lbl_venues, 1)
        venue_top.addWidget(self.cb_venue_inactive)
        venue_top.addWidget(self.btn_venue_add)
        venue_top.addWidget(self.btn_venue_edit)
        venue_top.addWidget(self.btn_venue_archive)

        self.tbl_venues = QTableWidget(0, 6)
        self.tbl_venues.setHorizontalHeaderLabels(["ID", "Название", "Тип спорта", "Вместимость", "Активен", "Комментарий"])
        self._style_table(self.tbl_venues)
        self.tbl_venues.doubleClicked.connect(self._venue_edit)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        right.addLayout(venue_top)
        right.addWidget(self.tbl_venues, 1)

        # ---------- Root
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(12)
        root.addLayout(left, 1)
        root.addLayout(right, 1)

        self.reload_orgs()

    # -------- helpers
    def _is_admin(self) -> bool:
        return (self.user.role_code or "").lower() == "admin"

    def _org_access(self, org_id: int):
        return get_org_access(user_id=self.user.id, role_code=self.user.role_code, org_id=org_id)

    def _apply_ui_access(self):
        org = self._selected_org()

        # create org: только admin (как в сервисе create_org)
        self.btn_org_add.setEnabled(self._is_admin())

        if not org:
            self.btn_org_edit.setEnabled(False)
            self.btn_org_archive.setEnabled(False)

            self.btn_venue_add.setEnabled(False)
            self.btn_venue_edit.setEnabled(False)
            self.btn_venue_archive.setEnabled(False)
            return

        acc = self._org_access(org.id)
        self.btn_org_edit.setEnabled(acc.can_edit)
        self.btn_org_archive.setEnabled(acc.can_edit)

        # Площадки завязаны на право редактирования учреждения
        self.btn_venue_add.setEnabled(acc.can_edit)
        self.btn_venue_edit.setEnabled(acc.can_edit)
        self.btn_venue_archive.setEnabled(acc.can_edit)

    def _on_org_selected(self):
        self._apply_ui_access()
        self.reload_venues()

    def _style_table(self, tbl: QTableWidget) -> None:
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setSortingEnabled(True)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        tbl.setStyleSheet(_TABLE_QSS)

        header = tbl.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        tbl.setFont(f)

        for c in range(tbl.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(tbl.columnCount() - 1, QHeaderView.ResizeMode.Stretch)

    # -------- selection helpers
    def _selected_org(self) -> SportOrg | None:
        row = self.tbl_orgs.currentRow()
        if row < 0:
            return None
        item = self.tbl_orgs.item(row, 0)
        if not item:
            return None
        obj = item.data(Qt.UserRole)
        return obj if isinstance(obj, SportOrg) else None

    def _selected_venue(self) -> Venue | None:
        row = self.tbl_venues.currentRow()
        if row < 0:
            return None
        item = self.tbl_venues.item(row, 0)
        if not item:
            return None
        obj = item.data(Qt.UserRole)
        return obj if isinstance(obj, Venue) else None

    def _org_work_str(self, o: SportOrg) -> str:
        if getattr(o, "is_24h", False):
            return "24/7"
        ws = getattr(o, "work_start", None)
        we = getattr(o, "work_end", None)
        if ws and we:
            return f"{ws:%H:%M}–{we:%H:%M}"
        return "—"

    # -------- reloaders
    def reload_orgs(self):
        selected = self._selected_org()
        selected_id = selected.id if selected else None

        try:
            orgs = list_orgs(
                user_id=self.user.id,
                role_code=self.user.role_code,
                search=self.ed_org_search.text(),
                include_inactive=self.cb_org_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Учреждения", f"Ошибка загрузки:\n{e}")
            return

        self.tbl_orgs.setSortingEnabled(False)
        self.tbl_orgs.setRowCount(0)

        for o in orgs:
            r = self.tbl_orgs.rowCount()
            self.tbl_orgs.insertRow(r)

            it_id = QTableWidgetItem(str(o.id))
            it_id.setData(Qt.UserRole, o)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_work = QTableWidgetItem(self._org_work_str(o))
            it_work.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_active = QTableWidgetItem("Да" if o.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl_orgs.setItem(r, 0, it_id)
            self.tbl_orgs.setItem(r, 1, QTableWidgetItem(o.name))
            self.tbl_orgs.setItem(r, 2, QTableWidgetItem(o.address or ""))
            self.tbl_orgs.setItem(r, 3, it_work)
            self.tbl_orgs.setItem(r, 4, it_active)

            if not o.is_active:
                for c in range(self.tbl_orgs.columnCount()):
                    it = self.tbl_orgs.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

        self.tbl_orgs.setSortingEnabled(True)

        if selected_id is not None:
            self._select_org_row_by_id(selected_id)

        self._apply_ui_access()
        self.reload_venues()

    def reload_venues(self):
        org = self._selected_org()
        if not org:
            self.lbl_venues.setText("Площадки: (выберите учреждение слева)")
            self.tbl_venues.setRowCount(0)
            return

        self.lbl_venues.setText(f"Площадки: {org.name}")

        selected = self._selected_venue()
        selected_id = selected.id if selected else None

        try:
            venues = list_venues(org.id, include_inactive=self.cb_venue_inactive.isChecked())
        except Exception as e:
            QMessageBox.critical(self, "Площадки", f"Ошибка загрузки:\n{e}")
            return

        self.tbl_venues.setSortingEnabled(False)
        self.tbl_venues.setRowCount(0)

        for v in venues:
            r = self.tbl_venues.rowCount()
            self.tbl_venues.insertRow(r)

            it_id = QTableWidgetItem(str(v.id))
            it_id.setData(Qt.UserRole, v)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_cap = QTableWidgetItem("" if v.capacity is None else str(v.capacity))
            it_cap.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_active = QTableWidgetItem("Да" if v.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl_venues.setItem(r, 0, it_id)
            self.tbl_venues.setItem(r, 1, QTableWidgetItem(v.name))
            self.tbl_venues.setItem(r, 2, QTableWidgetItem(v.sport_type or ""))
            self.tbl_venues.setItem(r, 3, it_cap)
            self.tbl_venues.setItem(r, 4, it_active)
            self.tbl_venues.setItem(r, 5, QTableWidgetItem(v.comment or ""))

            if not v.is_active:
                for c in range(self.tbl_venues.columnCount()):
                    it = self.tbl_venues.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

        self.tbl_venues.setSortingEnabled(True)

        if selected_id is not None:
            self._select_venue_row_by_id(selected_id)

        self._apply_ui_access()

    # -------- org actions
    def _org_add(self):
        if not self._is_admin():
            QMessageBox.warning(self, "Доступ запрещён", "Создание учреждения доступно только администратору.")
            return

        dlg = OrgDialog(self, title="Создать учреждение")
        if dlg.exec() != OrgDialog.Accepted:
            return

        data = dlg.values()
        try:
            new_id = create_org(
                user_id=self.user.id,
                role_code=self.user.role_code,
                name=data["name"],
                address=data["address"],
                comment=data["comment"],
                work_start=data["work_start"],
                work_end=data["work_end"],
                is_24h=data["is_24h"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Создать учреждение", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Учреждения", f"Создано учреждение (id={new_id}).")
        self.reload_orgs()
        self._select_org_row_by_id(new_id)

    def _org_edit(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Редактировать", "Выберите учреждение.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование этого учреждения.")
            return

        dlg = OrgDialog(
            self,
            title=f"Редактировать: {org.name}",
            data={
                "name": org.name,
                "address": org.address,
                "comment": org.comment,
                "work_start": getattr(org, "work_start", None),
                "work_end": getattr(org, "work_end", None),
                "is_24h": getattr(org, "is_24h", False),
            },
        )
        if dlg.exec() != OrgDialog.Accepted:
            return

        data = dlg.values()
        try:
            update_org(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                name=data["name"],
                address=data["address"],
                comment=data["comment"],
                work_start=data["work_start"],
                work_end=data["work_end"],
                is_24h=data["is_24h"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Редактировать учреждение", f"Ошибка:\n{e}")
            return

        self.reload_orgs()
        self._select_org_row_by_id(org.id)

    def _org_toggle(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Архив", "Выберите учреждение.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на изменение статуса этого учреждения.")
            return

        new_state = not org.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы действительно хотите {action} учреждение «{org.name}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_org_active(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                is_active=new_state,
            )
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload_orgs()

    # -------- venue actions (UI-гейт по правам учреждения)
    def _venue_add(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Площадки", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование площадок этого учреждения.")
            return

        dlg = VenueDialog(self, title=f"Создать площадку — {org.name}")
        if dlg.exec() != VenueDialog.Accepted:
            return

        data = dlg.values()
        try:
            new_id = create_venue(
                org_id=org.id,
                name=data["name"],
                sport_type=data["sport_type"],
                capacity=data["capacity"],
                comment=data["comment"],
            )
            apply_units_scheme(new_id, data["units_scheme"])
        except Exception as e:
            QMessageBox.critical(self, "Создать площадку", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Площадки", f"Создана площадка (id={new_id}).")
        self.reload_venues()
        self._select_venue_row_by_id(new_id)

    def _venue_edit(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Редактировать", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование площадок этого учреждения.")
            return

        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Редактировать", "Выберите площадку.")
            return

        dlg = VenueDialog(
            self,
            title=f"Редактировать площадку: {v.name}",
            data={
                "id": v.id,
                "name": v.name,
                "sport_type": v.sport_type,
                "capacity": v.capacity,
                "comment": v.comment,
            },
        )
        if dlg.exec() != VenueDialog.Accepted:
            return

        data = dlg.values()
        try:
            update_venue(
                venue_id=v.id,
                name=data["name"],
                sport_type=data["sport_type"],
                capacity=data["capacity"],
                comment=data["comment"],
            )
            apply_units_scheme(v.id, data["units_scheme"])
        except Exception as e:
            QMessageBox.critical(self, "Редактировать площадку", f"Ошибка:\n{e}")
            return

        self.reload_venues()
        self._select_venue_row_by_id(v.id)

    def _venue_toggle(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Архив", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на изменение статуса площадок этого учреждения.")
            return

        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Архив", "Выберите площадку.")
            return

        new_state = not v.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы действительно хотите {action} площадку «{v.name}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_venue_active(v.id, new_state)
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload_venues()

    # -------- selection by id
    def _select_org_row_by_id(self, org_id: int) -> None:
        for r in range(self.tbl_orgs.rowCount()):
            item = self.tbl_orgs.item(r, 0)
            if item and item.text() == str(org_id):
                self.tbl_orgs.setCurrentCell(r, 0)
                self.tbl_orgs.scrollToItem(item)
                return

    def _select_venue_row_by_id(self, venue_id: int) -> None:
        for r in range(self.tbl_venues.rowCount()):
            item = self.tbl_venues.item(r, 0)
            if item and item.text() == str(venue_id):
                self.tbl_venues.setCurrentCell(r, 0)
                self.tbl_venues.scrollToItem(item)
                return
