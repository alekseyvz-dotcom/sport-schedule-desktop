from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Tuple, Optional

import os
import tempfile
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QBrush
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
    QHeaderView,
)

from app.services.ref_service import list_active_orgs, list_active_venues, list_active_tenants
from app.services.venue_units_service import list_venue_units
from app.services.bookings_service import (
    list_bookings_for_day,
    create_booking,
    update_booking,
    cancel_booking,
)
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


# Более “аккуратная” таблица:
# - видимая дорогая сетка
# - мягкая подсветка выделения (без убийства ваших цветов брони)
# - чуть аккуратнее padding/line-height
_TABLE_QSS = """
QTableWidget {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;

    gridline-color: #e9edf3;
    selection-background-color: #00000000; /* прозрачно: не перекрывает setBackground */
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
    background: #00000000; /* важно: не затираем цвет слота */
}
"""


_PAGE_QSS = """
QWidget {
    background: #fbfbfc;
}
QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 22px;
}
QComboBox:focus, QDateEdit:focus {
    border: 1px solid #7fb3ff;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 600;
    min-height: 34px;
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


class SchedulePage(QWidget):
    WORK_START = time(8, 0)
    WORK_END = time(22, 0)
    SLOT_MINUTES = 30

    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_PAGE_QSS)

        self.lbl_title = QLabel("Расписание")
        self.lbl_title.setObjectName("sectionTitle")

        self.cmb_org = QComboBox()
        self.cmb_org.currentIndexChanged.connect(self._on_org_changed)

        self.dt_day = QDateEdit()
        self.dt_day.setCalendarPopup(True)
        self.dt_day.setDate(date.today())
        self.dt_day.dateChanged.connect(lambda *_: self.reload())

        self.cb_cancelled = QCheckBox("Отменённые")
        self.cb_cancelled.setChecked(False)
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())

        self.btn_create = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_cancel = QPushButton("Отменить")
        self.btn_refresh = QPushButton("Обновить")

        self.btn_create.clicked.connect(self._on_create)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_refresh.clicked.connect(self.reload)

        top = QHBoxLayout()
        top.setContentsMargins(12, 12, 12, 8)
        top.setSpacing(10)
        top.addWidget(self.lbl_title)
        top.addWidget(QLabel("Учреждение:"))
        top.addWidget(self.cmb_org, 1)
        top.addWidget(QLabel("Дата:"))
        top.addWidget(self.dt_day)
        top.addWidget(self.cb_cancelled)
        top.addWidget(self.btn_create)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_cancel)
        top.addWidget(self.btn_refresh)

        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)

        # ВАЖНО: без “зебры”, с сеткой
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setShowGrid(True)
        self.tbl.setGridStyle(Qt.PenStyle.SolidLine)

        self.tbl.verticalHeader().setVisible(False)
        self.tbl.itemDoubleClicked.connect(lambda *_: self._on_edit())
        self.tbl.setStyleSheet(_TABLE_QSS)

        header = self.tbl.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self._resources: List[Resource] = []
        self._tenants: List[Dict] = []

        QTimer.singleShot(0, self._load_refs)

    # --------- Небольшие помощники для “аккуратной” заливки ---------

    def _base_color_for_booking(self, b) -> QColor:
        if getattr(b, "status", "") == "cancelled":
            return QColor("#cfd6df")  # мягкий серый
        # PD/прочее — более приятные пастельные тона
        if getattr(b, "kind", "") == "PD":
            return QColor("#7cc7ff")  # голубой
        return QColor("#7fe0a3")  # зелёный

    def _shade(self, c: QColor, factor: float) -> QColor:
        """
        factor > 1  -> светлее
        factor < 1  -> темнее
        """
        r = max(0, min(255, int(c.red() * factor)))
        g = max(0, min(255, int(c.green() * factor)))
        b = max(0, min(255, int(c.blue() * factor)))
        return QColor(r, g, b)

    def _apply_booking_cell_style(self, it: QTableWidgetItem, b, *, is_edge: bool) -> None:
        """
        Более аккуратная заливка:
        - внутри брони: ровный пастельный цвет
        - на границах брони (первый/последний слот): чуть темнее, чтобы читалась “полоса”
        - текст: тёмный
        """
        base = self._base_color_for_booking(b)
        fill = self._shade(base, 0.92 if is_edge else 1.05)  # границы чуть плотнее
        it.setBackground(QBrush(fill))
        it.setForeground(QBrush(QColor("#0f172a")))

    def _apply_selection_overlay(self) -> None:
        """
        “Красивое” выделение без QSS-перекраски:
        мы не меняем background (чтобы не убить booking color),
        а слегка подсвечиваем текст выбранных ячеек.
        """
        selected = set(self.tbl.selectedItems())
        for r in range(self.tbl.rowCount()):
            for c in range(self.tbl.columnCount()):
                it = self.tbl.item(r, c)
                if not it:
                    continue
                # не трогаем колонку времени
                if c == 0:
                    continue
                # если выбранно — делаем текст чуть темнее/жирнее
                f = it.font()
                if it in selected:
                    f.setBold(True)
                    it.setFont(f)
                else:
                    f.setBold(False)
                    it.setFont(f)

    # ----------------------------------------------------------------

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

        header = self.tbl.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(1, 1 + resource_count):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

        for r, tm in enumerate(times):
            it = QTableWidgetItem(tm.strftime("%H:%M"))
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl.setItem(r, 0, it)

        for r in range(len(times)):
            for c in range(1, 1 + resource_count):
                it = QTableWidgetItem("")
                it.setData(Qt.ItemDataRole.UserRole, None)
                self.tbl.setItem(r, c, it)

        self.tbl.setColumnWidth(0, 70)
        self.tbl.resizeRowsToContents()

    def _selected_multi_units(self) -> Optional[Tuple[List[int], int, int]]:
        items = self.tbl.selectedItems()
        if not items:
            return None

        cols = sorted({i.column() for i in items if i.column() != 0})
        if not cols:
            return None

        venue_ids = set()
        for col in cols:
            rsrc = self._resources[col - 1]
            venue_ids.add(int(rsrc.venue_id))
            if rsrc.venue_unit_id is None:
                QMessageBox.information(
                    self,
                    "Выделение",
                    "Можно выбирать несколько колонок только для зон одной площадки.",
                )
                return None

        if len(venue_ids) != 1:
            QMessageBox.information(
                self,
                "Выделение",
                "Можно бронировать несколько зон только в рамках одной площадки.",
            )
            return None

        rows = sorted({i.row() for i in items})
        return cols, rows[0], rows[-1]

    def _row_to_datetime(self, day: date, row: int) -> datetime:
        tm = self._time_slots()[row]
        return datetime.combine(day, tm, tzinfo=self.TZ)

    def _selected_booking(self):
        it = self.tbl.currentItem()
        if not it:
            return None
        return it.data(Qt.ItemDataRole.UserRole)

    def reload(self):
        # очистка
        for r in range(self.tbl.rowCount()):
            for c in range(1, self.tbl.columnCount()):
                it = self.tbl.item(r, c)
                if it is None:
                    it = QTableWidgetItem("")
                    self.tbl.setItem(r, c, it)
                it.setText("")
                it.setBackground(QBrush(QColor("#ffffff")))
                it.setForeground(QBrush(QColor("#111111")))
                f = it.font()
                f.setBold(False)
                it.setFont(f)
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

            for r in range(r0, r1 + 1):
                it = self.tbl.item(r, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.tbl.setItem(r, col, it)

                is_edge = (r == r0) or (r == r1)
                self._apply_booking_cell_style(it, b, is_edge=is_edge)
                it.setData(Qt.ItemDataRole.UserRole, b)

            it0 = self.tbl.item(r0, col)
            if it0:
                unit_suffix = f" [{b.venue_unit_name}]" if getattr(b, "venue_unit_name", "") else ""
                title = (b.title or "").strip()
                if title:
                    it0.setText(f"{b.kind}{unit_suffix} | {b.tenant_name}\n{title}")
                else:
                    it0.setText(f"{b.kind}{unit_suffix} | {b.tenant_name}")

        self.tbl.resizeRowsToContents()
        self._apply_selection_overlay()

    def _on_create(self):
        try:
            sel = self._selected_multi_units()
            if not sel:
                QMessageBox.information(
                    self,
                    "Создать бронь",
                    "Выделите диапазон времени и 1+ колонок зон ОДНОЙ площадки (не колонку 'Время').",
                )
                return

            cols, rmin, rmax = sel
            day = self.dt_day.date().toPython()

            starts_at = self._row_to_datetime(day, rmin)
            ends_at = self._row_to_datetime(day, rmax) + timedelta(minutes=self.SLOT_MINUTES)

            if not self._tenants:
                QMessageBox.warning(self, "Контрагенты", "Нет активных контрагентов. Сначала создайте контрагента.")
                return

            venue_name = self._resources[cols[0] - 1].venue_name

            dlg = BookingDialog(
                self,
                starts_at=starts_at,
                ends_at=ends_at,
                tenants=self._tenants,
                venue_name=venue_name,
                venue_units=None,
            )

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            data = dlg.values()

            created_ids: List[int] = []
            for col in cols:
                rsrc = self._resources[col - 1]
                new_id = create_booking(
                    venue_id=int(rsrc.venue_id),
                    venue_unit_id=(int(rsrc.venue_unit_id) if rsrc.venue_unit_id is not None else None),
                    tenant_id=data["tenant_id"],
                    title=data["title"],
                    kind=data["kind"],
                    starts_at=starts_at,
                    ends_at=ends_at,
                )
                created_ids.append(new_id)

            QMessageBox.information(self, "Расписание", f"Создано бронирований: {len(created_ids)}")
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

    def _on_edit(self):
        b = self._selected_booking()
        if not b:
            QMessageBox.information(self, "Редактировать", "Выберите ячейку с бронью.")
            return
        if getattr(b, "status", "") == "cancelled":
            QMessageBox.information(self, "Редактировать", "Отменённую бронь редактировать нельзя.")
            return

        rsrc = next((r for r in self._resources if r.venue_id == b.venue_id and r.venue_unit_id == b.venue_unit_id), None)
        venue_name = rsrc.resource_name if rsrc else f"Площадка {b.venue_id}"

        units = [{"id": u.id, "name": u.name} for u in list_venue_units(int(b.venue_id), include_inactive=False)]

        dlg = BookingDialog(
            self,
            title="Редактировать бронирование",
            starts_at=b.starts_at,
            ends_at=b.ends_at,
            tenants=self._tenants,
            venue_name=venue_name,
            venue_units=units,
            initial={
                "kind": getattr(b, "kind", "PD"),
                "tenant_id": getattr(b, "tenant_id", None),
                "venue_unit_id": getattr(b, "venue_unit_id", None),
                "title": getattr(b, "title", ""),
            },
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        try:
            update_booking(
                int(b.id),
                tenant_id=data["tenant_id"],
                title=data["title"],
                kind=data["kind"],
                venue_unit_id=data["venue_unit_id"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Редактировать бронирование", f"Ошибка:\n{e}")
            return

        self.reload()

    def _on_cancel(self):
        b = self._selected_booking()
        if not b:
            QMessageBox.information(self, "Отмена", "Выберите ячейку с бронью.")
            return
        if getattr(b, "status", "") == "cancelled":
            QMessageBox.information(self, "Отмена", "Бронь уже отменена.")
            return

        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                f"Отменить бронь:\n{getattr(b, 'tenant_name', '')}\n{getattr(b, 'title', '')}\n"
                f"{b.starts_at:%d.%m.%Y %H:%M} – {b.ends_at:%H:%M} ?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            cancel_booking(int(b.id))
        except Exception as e:
            QMessageBox.critical(self, "Отмена брони", f"Ошибка:\n{e}")
            return

        self.reload()
