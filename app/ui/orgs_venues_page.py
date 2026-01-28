from __future__ import annotations

from PySide6.QtCore import Qt
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
)

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


class OrgsVenuesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Orgs (left)
        self.ed_org_search = QLineEdit()
        self.ed_org_search.setPlaceholderText("Поиск учреждений: имя/адрес")
        self.ed_org_search.returnPressed.connect(self.reload_orgs)

        self.cb_org_inactive = QCheckBox("Показывать архив")
        self.cb_org_inactive.stateChanged.connect(lambda *_: self.reload_orgs())

        self.btn_org_add = QPushButton("Создать")
        self.btn_org_edit = QPushButton("Редактировать")
        self.btn_org_archive = QPushButton("Архивировать/восстановить")

        self.btn_org_add.clicked.connect(self._org_add)
        self.btn_org_edit.clicked.connect(self._org_edit)
        self.btn_org_archive.clicked.connect(self._org_toggle)

        org_top = QHBoxLayout()
        org_top.addWidget(self.ed_org_search, 1)
        org_top.addWidget(self.cb_org_inactive)
        org_top.addWidget(self.btn_org_add)
        org_top.addWidget(self.btn_org_edit)
        org_top.addWidget(self.btn_org_archive)

        self.tbl_orgs = QTableWidget(0, 4)
        self.tbl_orgs.setHorizontalHeaderLabels(["ID", "Название", "Адрес", "Активен"])
        self.tbl_orgs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_orgs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_orgs.itemSelectionChanged.connect(self.reload_venues)

        left = QVBoxLayout()
        left.addLayout(org_top)
        left.addWidget(self.tbl_orgs, 1)

        # --- Venues (right)
        self.lbl_venues = QLabel("Площадки: (выберите учреждение слева)")

        self.cb_venue_inactive = QCheckBox("Показывать архив")
        self.cb_venue_inactive.stateChanged.connect(lambda *_: self.reload_venues())

        self.btn_venue_add = QPushButton("Создать")
        self.btn_venue_edit = QPushButton("Редактировать")
        self.btn_venue_archive = QPushButton("Архивировать/восстановить")

        self.btn_venue_add.clicked.connect(self._venue_add)
        self.btn_venue_edit.clicked.connect(self._venue_edit)
        self.btn_venue_archive.clicked.connect(self._venue_toggle)

        venue_top = QHBoxLayout()
        venue_top.addWidget(self.lbl_venues, 1)
        venue_top.addWidget(self.cb_venue_inactive)
        venue_top.addWidget(self.btn_venue_add)
        venue_top.addWidget(self.btn_venue_edit)
        venue_top.addWidget(self.btn_venue_archive)

        self.tbl_venues = QTableWidget(0, 6)
        self.tbl_venues.setHorizontalHeaderLabels(
            ["ID", "Название", "Тип спорта", "Вместимость", "Активен", "Комментарий"]
        )
        self.tbl_venues.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_venues.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        right = QVBoxLayout()
        right.addLayout(venue_top)
        right.addWidget(self.tbl_venues, 1)

        # --- Root
        root = QHBoxLayout(self)
        root.addLayout(left, 1)
        root.addLayout(right, 1)

        self.reload_orgs()

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

    # -------- reloaders
    def reload_orgs(self):
        selected = self._selected_org()
        selected_id = selected.id if selected else None

        try:
            orgs = list_orgs(
                self.ed_org_search.text(),
                include_inactive=self.cb_org_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Учреждения", f"Ошибка загрузки:\n{e}")
            return

        self.tbl_orgs.setRowCount(0)
        for o in orgs:
            r = self.tbl_orgs.rowCount()
            self.tbl_orgs.insertRow(r)

            it_id = QTableWidgetItem(str(o.id))
            it_id.setData(Qt.UserRole, o)

            self.tbl_orgs.setItem(r, 0, it_id)
            self.tbl_orgs.setItem(r, 1, QTableWidgetItem(o.name))
            self.tbl_orgs.setItem(r, 2, QTableWidgetItem(o.address or ""))
            self.tbl_orgs.setItem(r, 3, QTableWidgetItem("Да" if o.is_active else "Нет"))

        self.tbl_orgs.resizeColumnsToContents()

        if selected_id is not None:
            self._select_org_row_by_id(selected_id)

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

        self.tbl_venues.setRowCount(0)
        for v in venues:
            r = self.tbl_venues.rowCount()
            self.tbl_venues.insertRow(r)

            it_id = QTableWidgetItem(str(v.id))
            it_id.setData(Qt.UserRole, v)

            self.tbl_venues.setItem(r, 0, it_id)
            self.tbl_venues.setItem(r, 1, QTableWidgetItem(v.name))
            self.tbl_venues.setItem(r, 2, QTableWidgetItem(v.sport_type or ""))
            self.tbl_venues.setItem(r, 3, QTableWidgetItem("" if v.capacity is None else str(v.capacity)))
            self.tbl_venues.setItem(r, 4, QTableWidgetItem("Да" if v.is_active else "Нет"))
            self.tbl_venues.setItem(r, 5, QTableWidgetItem(v.comment or ""))

        self.tbl_venues.resizeColumnsToContents()

        if selected_id is not None:
            self._select_venue_row_by_id(selected_id)

    # -------- org actions
    def _org_add(self):
        dlg = OrgDialog(self, title="Создать учреждение")
        if dlg.exec() != OrgDialog.Accepted:
            return

        try:
            new_id = create_org(**dlg.values())
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

        dlg = OrgDialog(
            self,
            title=f"Редактировать: {org.name}",
            data={"name": org.name, "address": org.address, "comment": org.comment},
        )
        if dlg.exec() != OrgDialog.Accepted:
            return

        try:
            update_org(org.id, **dlg.values())
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
            set_org_active(org.id, new_state)
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload_orgs()

    # -------- venue actions
    def _venue_add(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Площадки", "Сначала выберите учреждение слева.")
            return

        dlg = VenueDialog(self, title=f"Создать площадку — {org.name}")
        if dlg.exec() != VenueDialog.Accepted:
            return

        data = dlg.values()
        try:
            # ВАЖНО: create_venue не должен получать units_scheme
            new_id = create_venue(
                org_id=org.id,
                name=data["name"],
                sport_type=data["sport_type"],
                capacity=data["capacity"],
                comment=data["comment"],
            )
            # NEW: применяем схему зон (создаст половины/четверти)
            apply_units_scheme(new_id, data["units_scheme"])
        except Exception as e:
            QMessageBox.critical(self, "Создать площадку", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Площадки", f"Создана площадка (id={new_id}).")
        self.reload_venues()
        self._select_venue_row_by_id(new_id)

    def _venue_edit(self):
        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Редактировать", "Выберите площадку.")
            return

        dlg = VenueDialog(
            self,
            title=f"Редактировать площадку: {v.name}",
            data={
                "id": v.id,  # ВАЖНО: чтобы dialog подтянул текущую схему зон
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
            # NEW: применяем схему зон
            apply_units_scheme(v.id, data["units_scheme"])
        except Exception as e:
            QMessageBox.critical(self, "Редактировать площадку", f"Ошибка:\n{e}")
            return

        self.reload_venues()
        self._select_venue_row_by_id(v.id)

    def _venue_toggle(self):
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
