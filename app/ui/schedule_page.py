from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Tuple, Optional

import os
import tempfile
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QDateEdit,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QLabel,
    QAbstractItemView,
    QDialog,
)

from app.services.ref_service import list_active_orgs, list_active_venues, list_active_tenants
from app.services.venue_units_service import list_venue_units
from app.services.bookings_service import list_bookings_for_day, create_booking
from app.ui.booking_dialog import BookingDialog


def _uilog(msg: str) -> None:
    path = os.path.join(tempfile.gettempdir(), "schedule_debug.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")


@dataclass(frozen=True)
class Resource:
    venue_id: int
    venue_name: str
    venue_unit_id: int | None
    resource_name: str


class SchedulePage(QWidget):
    WORK_START = time(8, 0)
    WORK_END = time(22, 0)
    SLOT_MINUTES = 30

    # ВАЖНО: Postgres TIMESTAMPTZ -> aware datetime. Делаем UI-дату тоже aware.
    # Москва = UTC+3. Если другой регион — поменяйте значение.
    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    def __init__(self, parent=None):
        super().__init__(parent)

        self.cmb_org = QComboBox()
        self.cmb_org.currentIndexChanged.connect(self._on_org_changed)

        self.dt_day = QDateEdit()
        self.dt_day.setCalendarPopup(True)
        self.dt_day.setDate(date.today())
        self.dt_day.dateChanged.connect(lambda *_: self.reload())

        self.cb_cancelled = QCheckBox("Показывать отменённые")
        self.cb_cancelled.setChecked(False)
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())

        self.btn_create = QPushButton("Создать бронь")
        self.btn_refresh = QPushButton("Обновить")
        self.btn_create.clicked.connect(self._on_create)
        self.btn_refresh.clicked.connect(self.reload)

        top = QHBoxLayout()
        top.addWidget(QLabel("Учреждение:"))
        top.addWidget(self.cmb_org, 1)
        top.addWidget(QLabel("Дата:"))
        top.addWidget(self.dt_day)
        top.addWidget(self.cb_cancelled)
        top.addWidget(self.btn_create)
        top.addWidget(self.btn_refresh)

        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        # ресурсы расписания: либо venue целиком, либо venue_unit
        self._resources: List[Resource] = []
        self._tenants: List[Dict] = []

        self._load_refs()

    def _load_refs(self):
        try:
            orgs = list_active_orgs()
            self.cmb_org.blockSignals(True)
            self.cmb_org.clear()
            for o in orgs:
                self.cmb_org.addItem(o.name, o.id)
            self.cmb_org.blockSignals(False)

            self._tenants = [{"id": t.id, "name": t.name} for t in list_active_tenants()]
        except Exception as e:
            QMessageBox.critical(self, "Справочники", f"Ошибка загрузки справочников:\n{e}")
            return

        self._on_org_changed()

    def _on_org_changed(self):
        org_id = self.cmb_org.currentData()
        if org_id is None:
            self._resources = []
            self._setup_table()
            return

        try:
            venues = list_active_venues(int(org_id))

            resources: List[Resource] = []
            for v in venues:
                units = list_venue_units(v.id, include_inactive=False)
                if units:
                    for u in units:
                        resources.append(
                            Resource(
                                venue_id=v.id,
                                venue_name=v.name,
                                venue_unit_id=u.id,
                                resource_name=f"{v.name} — {u.name}",
                            )
                        )
                else:
                    resources.append(
                        Resource(
                            venue_id=v.id,
                            venue_name=v.name,
                            venue_unit_id=None,
                            resource_name=v.name,
                        )
                    )

            self._resources = resources

        except Exception as e:
            QMessageBox.critical(self, "Площадки", f"Ошибка загрузки площадок:\n{e}")
            self._resources = []

        self._setup_table()
        self.reload()

    def _time_slots(self) -> List[time]:
        out: List[time] = []
        cur = datetime.combine(date.today(), self.WORK_START)
        end = datetime.combine(date.today(), self.WORK_END)
        step = timedelta(minutes=self.SLOT_MINUTES)
        while cur < end:
            out.append(cur.time())
            cur += step
        return out

    def _setup_table(self):
        times = self._time_slots()
        resource_count = len(self._resources)

        self.tbl.clear()
        self.tbl.setRowCount(len(times))
        self.tbl.setColumnCount(1 + resource_count)

        headers = ["Время"] + [r.resource_name for r in self._resources]
        self.tbl.setHorizontalHeaderLabels(headers)

        for r, tm in enumerate(times):
            it = QTableWidgetItem(tm.strftime("%H:%M"))
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tbl.setItem(r, 0, it)

        # создаём item в каждой ячейке ресурсов
        for r in range(len(times)):
            for c in range(1, 1 + resource_count):
                it = QTableWidgetItem("")
                it.setData(Qt.ItemDataRole.UserRole, None)
                self.tbl.setItem(r, c, it)

        self.tbl.resizeColumnsToContents()
        self.tbl.setColumnWidth(0, 70)

    def _selected_range(self) -> Optional[Tuple[int, int, int]]:
        items = self.tbl.selectedItems()
        if not items:
            return None

        cols_all = sorted({i.column() for i in items})
        cols = {i.column() for i in items if i.column() != 0}
        if len(cols) != 1:
            QMessageBox.information(self, "Выделение", f"Выделены колонки: {cols_all} (нужно ровно 1 ресурс)")
            return None

        col = next(iter(cols))
        rows = sorted({i.row() for i in items})
        return col, rows[0], rows[-1]

    def _row_to_datetime(self, day: date, row: int) -> datetime:
        tm = self._time_slots()[row]
        return datetime.combine(day, tm, tzinfo=self.TZ)

    def reload(self):
        # очистка
        for r in range(self.tbl.rowCount()):
            for c in range(1, self.tbl.columnCount()):
                it = self.tbl.item(r, c)
                if it is None:
                    it = QTableWidgetItem("")
                    self.tbl.setItem(r, c, it)
                it.setText("")
                it.setBackground(Qt.GlobalColor.white)
                it.setData(Qt.ItemDataRole.UserRole, None)

        if not self._resources:
            return

        day = self.dt_day.date().toPython()
        include_cancelled = self.cb_cancelled.isChecked()
        venue_ids = sorted({rsrc.venue_id for rsrc in self._resources})

        try:
            bookings = list_bookings_for_day(venue_ids, day, include_cancelled=include_cancelled)
        except Exception as e:
            QMessageBox.critical(self, "Расписание", f"Ошибка загрузки бронирований:\n{e}")
            return

        # колонки по unit и (fallback) по venue
        unit_col: Dict[int, int] = {}
        venue_fallback_col: Dict[int, int] = {}
        for i, rsrc in enumerate(self._resources):
            col = i + 1
            if rsrc.venue_unit_id is not None:
                unit_col[int(rsrc.venue_unit_id)] = col
            else:
                venue_fallback_col[int(rsrc.venue_id)] = col

        day_start = datetime.combine(day, self.WORK_START, tzinfo=self.TZ)
        day_end = datetime.combine(day, self.WORK_END, tzinfo=self.TZ)

        for b in bookings:
            col = None
            if getattr(b, "venue_unit_id", None) is not None:
                col = unit_col.get(int(b.venue_unit_id))
            if col is None:
                col = venue_fallback_col.get(int(b.venue_id))
            if not col:
                continue

            start = max(b.starts_at, day_start)
            end = min(b.ends_at, day_end)
            if end <= start:
                continue

            r0 = int((start - day_start).total_seconds() // (self.SLOT_MINUTES * 60))
            r1 = int(((end - day_start).total_seconds() - 1) // (self.SLOT_MINUTES * 60))
            r0 = max(0, r0)
            r1 = min(self.tbl.rowCount() - 1, r1)

            if b.status == "cancelled":
                color = Qt.GlobalColor.lightGray
            else:
                color = Qt.GlobalColor.cyan if b.kind == "PD" else Qt.GlobalColor.green

            for r in range(r0, r1 + 1):
                it = self.tbl.item(r, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.tbl.setItem(r, col, it)
                it.setBackground(color)
                it.setData(Qt.ItemDataRole.UserRole, b)

            it0 = self.tbl.item(r0, col)
            if it0:
                unit_suffix = f" [{b.venue_unit_name}]" if getattr(b, "venue_unit_name", "") else ""
                it0.setText(f"{b.kind}{unit_suffix} | {b.tenant_name}\n{b.title}")

        self.tbl.resizeRowsToContents()

    def _on_create(self):
        try:
            _uilog("entered _on_create")

            sel = self._selected_range()
            if not sel:
                _uilog("no selection range")
                QMessageBox.information(
                    self,
                    "Создать бронь",
                    "Выделите диапазон слотов в одной колонке (не в колонке 'Время').",
                )
                return

            col, rmin, rmax = sel
            day = self.dt_day.date().toPython()

            res_idx = col - 1
            rsrc = self._resources[res_idx]

            starts_at = self._row_to_datetime(day, rmin)
            ends_at = self._row_to_datetime(day, rmax) + timedelta(minutes=self.SLOT_MINUTES)

            _uilog(
                "selection: "
                f"venue_id={rsrc.venue_id}, venue_unit_id={rsrc.venue_unit_id}, "
                f"starts_at={starts_at!r}, ends_at={ends_at!r}"
            )

            if not self._tenants:
                _uilog("no tenants")
                QMessageBox.warning(self, "Контрагенты", "Нет активных контрагентов. Сначала создайте контрагента.")
                return

            dlg = BookingDialog(
                self,
                starts_at=starts_at,
                ends_at=ends_at,
                tenants=self._tenants,
                venue_name=rsrc.resource_name,
            )

            res = dlg.exec()
            _uilog(f"dlg.exec()={res}, Accepted={int(QDialog.DialogCode.Accepted)}")

            if res != QDialog.DialogCode.Accepted:
                _uilog("dialog rejected")
                return

            data = dlg.values()
            _uilog(f"dialog values: {data!r}")

            _uilog("calling create_booking()")
            new_id = create_booking(
                venue_id=rsrc.venue_id,
                venue_unit_id=rsrc.venue_unit_id,
                tenant_id=data["tenant_id"],
                title=data["title"],
                kind="PD",
                starts_at=starts_at,
                ends_at=ends_at,
            )
            _uilog(f"create_booking OK id={new_id}")

            QMessageBox.information(self, "Расписание", f"Бронь создана (id={new_id}).")
            self.reload()

        except Exception as e:
            _uilog("UNHANDLED ERROR in _on_create: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(
                self,
                "Создать бронь",
                "Непредвиденная ошибка. Смотрите лог:\n"
                f"{os.path.join(tempfile.gettempdir(), 'schedule_debug.log')}\n\n"
                f"{repr(e)}",
            )
