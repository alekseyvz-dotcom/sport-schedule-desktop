# app/ui/venue_seasons_manage_dialog.py
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QHeaderView,
    QFormLayout, QSpinBox, QDateEdit, QLineEdit, QDialogButtonBox
)

from app.services.venue_seasons_service import (
    list_season_overrides,
    upsert_season_override,
    set_season_override_active,
    VenueSeasonOverride,
)


class _SeasonEditDialog(QDialog):
    def __init__(self, parent=None, *, year: int, title: str = "", date_from: date | None = None, date_to: date | None = None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Сезон на год")

        self.sp_year = QSpinBox()
        self.sp_year.setRange(2000, 2100)
        self.sp_year.setValue(int(year))

        self.ed_title = QLineEdit(title or "")

        self.dt_from = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("dd.MM.yyyy")

        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("dd.MM.yyyy")

        # дефолт: весь год
        y = int(year)
        df = date_from or date(y, 1, 1)
        dt = date_to or date(y, 12, 31)

        self.dt_from.setDate(QDate(df.year, df.month, df.day))
        self.dt_to.setDate(QDate(dt.year, dt.month, dt.day))

        form = QFormLayout()
        form.addRow("Год *:", self.sp_year)
        form.addRow("Название:", self.ed_title)
        form.addRow("С *:", self.dt_from)
        form.addRow("По *:", self.dt_to)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(form)
        root.addWidget(buttons)

    def _accept(self):
        y = int(self.sp_year.value())
        df = self.dt_from.date()
        dt = self.dt_to.date()

        dfrom = date(df.year(), df.month(), df.day())
        dto = date(dt.year(), dt.month(), dt.day())

        if dto < dfrom:
            QMessageBox.warning(self, "Сезон", "Дата 'По' должна быть >= даты 'С'.")
            return
        if dfrom.year != y or dto.year != y:
            QMessageBox.warning(self, "Сезон", "Дата 'С' и 'По' должны быть в выбранном году.")
            return

        self.accept()

    def values(self):
        y = int(self.sp_year.value())
        df = self.dt_from.date()
        dt = self.dt_to.date()
        return {
            "season_year": y,
            "title": (self.ed_title.text() or "").strip(),
            "date_from": date(df.year(), df.month(), df.day()),
            "date_to": date(dt.year(), dt.month(), dt.day()),
        }


class VenueSeasonsManageDialog(QDialog):
    def __init__(self, parent=None, *, user_id: int, role_code: str, venue_id: int):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Сезонность площадки (по годам)")

        self.user_id = user_id
        self.role_code = role_code
        self.venue_id = venue_id

        self.cb_inactive = QCheckBox("Показывать неактивные")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Добавить/обновить год…")
        self.btn_toggle = QPushButton("Активировать/деактивировать")

        self.btn_add.clicked.connect(self._add_or_update)
        self.btn_toggle.clicked.connect(self._toggle)

        top = QHBoxLayout()
        top.addWidget(self.cb_inactive, 1)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_toggle)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["ID", "Год", "С", "По", "Активно", "Название"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(False)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.doubleClicked.connect(self._add_or_update)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self.reload()

    def _selected(self) -> VenueSeasonOverride | None:
        r = self.tbl.currentRow()
        if r < 0:
            return None
        it = self.tbl.item(r, 0)
        obj = it.data(Qt.UserRole) if it else None
        return obj if isinstance(obj, VenueSeasonOverride) else None

    def reload(self):
        try:
            rows = list_season_overrides(
                user_id=self.user_id,
                role_code=self.role_code,
                venue_id=self.venue_id,
                include_inactive=self.cb_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Сезонность", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for x in rows:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(x.id))
            it_id.setData(Qt.UserRole, x)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_year = QTableWidgetItem(str(x.season_year))
            it_from = QTableWidgetItem(x.date_from.strftime("%d.%m.%Y"))
            it_to = QTableWidgetItem(x.date_to.strftime("%d.%m.%Y"))
            it_act = QTableWidgetItem("Да" if x.is_active else "Нет")
            it_title = QTableWidgetItem(x.title or "")

            it_act.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, it_year)
            self.tbl.setItem(r, 2, it_from)
            self.tbl.setItem(r, 3, it_to)
            self.tbl.setItem(r, 4, it_act)
            self.tbl.setItem(r, 5, it_title)

            if not x.is_active:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

    def _add_or_update(self):
        sel = self._selected()
        default_year = sel.season_year if sel else date.today().year

        dlg = _SeasonEditDialog(
            self,
            year=default_year,
            title=(sel.title if sel else ""),
            date_from=(sel.date_from if sel else None),
            date_to=(sel.date_to if sel else None),
        )
        if dlg.exec() != QDialog.Accepted:
            return

        v = dlg.values()
        try:
            upsert_season_override(
                user_id=self.user_id,
                role_code=self.role_code,
                venue_id=self.venue_id,
                season_year=v["season_year"],
                date_from=v["date_from"],
                date_to=v["date_to"],
                title=v["title"],
                is_active=True,
            )
        except Exception as e:
            QMessageBox.critical(self, "Сезонность", f"Ошибка сохранения:\n{e}")
            return

        self.reload()

    def _toggle(self):
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "Сезонность", "Выберите запись.")
            return

        new_state = not bool(sel.is_active)
        action = "активировать" if new_state else "деактивировать"
        if (
            QMessageBox.question(self, "Подтверждение", f"Вы действительно хотите {action} сезон?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_season_override_active(
                user_id=self.user_id,
                role_code=self.role_code,
                venue_id=self.venue_id,
                override_id=sel.id,
                is_active=new_state,
            )
        except Exception as e:
            QMessageBox.critical(self, "Сезонность", f"Ошибка:\n{e}")
            return

        self.reload()
