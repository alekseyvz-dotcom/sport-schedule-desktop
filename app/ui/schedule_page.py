from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Tuple, Optional

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
)

from app.services.ref_service import list_active_orgs, list_active_venues, list_active_tenants
from app.services.bookings_service import list_bookings_for_day, create_booking, Booking
from app.ui.booking_dialog import BookingDialog


@dataclass(frozen=True)
class SlotKey:
    venue_id: int
    starts_at: datetime


class SchedulePage(QWidget):
    WORK_START = time(8, 0)
    WORK_END = time(22, 0)
    SLOT_MINUTES = 30

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

        # ВАЖНО: чтобы можно было выделять "пустые" ячейки,
        # они должны существовать. Мы заполним их в _setup_table().
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        # caches
        self._venues: List[Tuple[int, str]] = []  # [(id, name)]
        self._tenants: List[Dict] = []            # [{id, name}]

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
            self._venues = []
            self._setup_table()
            return

        try:
            venues = list_active_venues(int(org_id))
            self._venues = [(v.id, v.name) for v in venues]
        except Exception as e:
            QMessageBox.critical(self, "Площадки", f"Ошибка загрузки площадок:\n{e}")
            self._venues = []

        self._setup_table()
        self.reload()

    def _time_slots(self) -> List[time]:
        out = []
        cur = datetime.combine(date.today(), self.WORK_START)
        end = datetime.combine(date.today(), self.WORK_END)
        step = timedelta(minutes=self.SLOT_MINUTES)
        while cur < end:
            out.append(cur.time())
            cur += step
        return out

    def _setup_table(self):
        times = self._time_slots()
        venue_count = len(self._venues)

        self.tbl.clear()
        self.tbl.setRowCount(len(times))
        self.tbl.setColumnCount(1 + venue_count)

        headers = ["Время"] + [name for (_, name) in self._venues]
        self.tbl.setHorizontalHeaderLabels(headers)

        # Колонка времени
        for r, tm in enumerate(times):
            it = QTableWidgetItem(tm.strftime("%H:%M"))
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)  # время не выделяем
            self.tbl.setItem(r, 0, it)

        # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ:
        # Создаём item для КАЖДОЙ ячейки площадок, иначе Qt не даст её выделить,
        # и selectedItems() будет пустым.
        for r in range(len(times)):
            for c in range(1, 1 + venue_count):
                it = QTableWidgetItem("")
                it.setData(Qt.ItemDataRole.UserRole, None)
                self.tbl.setItem(r, c, it)

        self.tbl.resizeColumnsToContents()
        self.tbl.setColumnWidth(0, 70)

    def _selected_range(self) -> Optional[Tuple[int, int, int]]:
        # (col, row_min, row_max) если выделение в одной колонке площадки
        items = self.tbl.selectedItems()
        if not items:
            return None

        cols = {i.column() for i in items if i.column() != 0}
        if len(cols) != 1:
            return None
        col = next(iter(cols))

        rows = sorted({i.row() for i in items})
        return col, rows[0], rows[-1]

    def _row_to_datetime(self, day: date, row: int) -> datetime:
        tm = self._time_slots()[row]
        return datetime.combine(day, tm)

    def reload(self):
        # очищаем раскраску/тексты (кроме колонки времени)
        for r in range(self.tbl.rowCount()):
            for c in range(1, self.tbl.columnCount()):
                it = self.tbl.item(r, c)
                if it is None:
                    # на всякий случай, но после _setup_table такого быть не должно
                    it = QTableWidgetItem("")
                    self.tbl.setItem(r, c, it)

                it.setText("")
                it.setBackground(Qt.GlobalColor.white)
                it.setData(Qt.ItemDataRole.UserRole, None)

        if not self._venues:
            return

        day = self.dt_day.date().toPython()
        include_cancelled = self.cb_cancelled.isChecked()
        venue_ids = [vid for (vid, _) in self._venues]

        try:
            bookings = list_bookings_for_day(venue_ids, day, include_cancelled=include_cancelled)
        except Exception as e:
            QMessageBox.critical(self, "Расписание", f"Ошибка загрузки бронирований:\n{e}")
            return

        venue_col: Dict[int, int] = {vid: i + 1 for i, (vid, _) in enumerate(self._venues)}
        day_start = datetime.combine(day, self.WORK_START)
        day_end = datetime.combine(day, self.WORK_END)

        for b in bookings:
            col = venue_col.get(b.venue_id)
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
                it0.setText(f"{b.kind} | {b.tenant_name}\n{b.title}")

        self.tbl.resizeRowsToContents()

    def _on_create(self):
        sel = self._selected_range()
        if not sel:
            QMessageBox.information(
                self,
                "Создать бронь",
                "Выделите диапазон слотов в одной колонке площадки (не в колонке 'Время').",
            )
            return

        col, rmin, rmax = sel
        day = self.dt_day.date().toPython()

        venue_idx = col - 1
        venue_id, venue_name = self._venues[venue_idx]

        starts_at = self._row_to_datetime(day, rmin)
        ends_at = self._row_to_datetime(day, rmax) + timedelta(minutes=self.SLOT_MINUTES)

        if not self._tenants:
            QMessageBox.warning(self, "Арендаторы", "Нет активных арендаторов. Сначала создайте арендатора.")
            return

        dlg = BookingDialog(
            self,
            starts_at=starts_at,
            ends_at=ends_at,
            tenants=self._tenants,
            venue_name=venue_name,
        )
        if dlg.exec() != dlg.Accepted:
            return

        data = dlg.values()
        try:
            create_booking(
                venue_id=venue_id,
                tenant_id=data["tenant_id"],
                title=data["title"],
                kind=data["kind"],
                starts_at=starts_at,
                ends_at=ends_at,
            )
        except Exception as e:
            QMessageBox.critical(self, "Создать бронь", f"Ошибка:\n{e}")
            return

        self.reload()
