from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from psycopg2.extras import RealDictCursor

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QDateEdit, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView
)

from app.db import get_conn, put_conn
from app.services.users_service import AuthUser
from app.services.access_service import list_allowed_org_ids, get_org_access
from app.services.ref_service import list_active_orgs_by_ids
from app.services.ref_service import list_active_venues
from app.services.venue_units_service import list_venue_units


TZ = timezone(timedelta(hours=3))

# Цвета как в вашей палитре
BG_BASE = QColor("#0b1220")
BG_CARD = QColor("#0f172a")
BORDER = QColor(255, 255, 255, 20)
TEXT = QColor(226, 232, 240)
TEXT_DIM = QColor(226, 232, 240, 140)


def _load_org_work_window(org_id: int) -> tuple[time, time, bool]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT work_start, work_end, is_24h
                FROM public.sport_orgs
                WHERE id=%s
                """,
                (int(org_id),),
            )
            row = cur.fetchone()
            if not row:
                return time(8, 0), time(22, 0), False
            if bool(row.get("is_24h")):
                return time(0, 0), time(23, 59, 59), True
            return row["work_start"], row["work_end"], False
    finally:
        if conn:
            put_conn(conn)


@dataclass(frozen=True)
class Resource:
    venue_id: int
    venue_unit_id: Optional[int]
    name: str
    venue_name: str


def _week_range(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())  # Пн
    return start, start + timedelta(days=6)            # Вс


def _overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    s = max(a0, b0)
    e = min(a1, b1)
    return max(0, int((e - s).total_seconds()))


def _sec_between(t0: time, t1: time) -> int:
    return int(
        (datetime.combine(date.today(), t1) - datetime.combine(date.today(), t0)).total_seconds()
    )


def _load_resources_for_org(org_id: int) -> List[Resource]:
    venues = list_active_venues(org_id)
    out: List[Resource] = []

    for v in venues:
        units = list_venue_units(v.id, include_inactive=False)
        if units:
            units_sorted = sorted(units, key=lambda u: (int(getattr(u, "sort_order", 0)), str(u.name)))
            for u in units_sorted:
                out.append(Resource(
                    venue_id=int(v.id),
                    venue_unit_id=int(u.id),
                    name=f"{v.name} — {u.name}",
                    venue_name=str(v.name),
                ))
        else:
            out.append(Resource(
                venue_id=int(v.id),
                venue_unit_id=None,
                name=str(v.name),
                venue_name=str(v.name),
            ))

    out.sort(key=lambda r: (r.venue_name, r.name))
    return out


def _load_bookings_for_week(org_id: int, start_dt: datetime, end_dt: datetime, include_cancelled: bool) -> list[dict]:
    cancel = "" if include_cancelled else "AND b.status <> 'cancelled'"
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT b.id, b.venue_id, b.venue_unit_id, b.starts_at, b.ends_at, b.status
                FROM bookings b
                JOIN venues v ON v.id = b.venue_id
                WHERE v.org_id = %s
                  AND b.starts_at < %s AND b.ends_at > %s
                  {cancel}
                """,
                (int(org_id), end_dt, start_dt),
            )
            return cur.fetchall() or []
    finally:
        if conn:
            put_conn(conn)


def _heat_level(pct: float) -> int:
    # как на вебе: 0..5
    if pct < 1:
        return 0
    if pct < 26:
        return 1
    if pct < 51:
        return 2
    if pct < 76:
        return 3
    if pct < 101:
        return 4
    return 5


def _level_color(level: int) -> QColor:
    # близко к веб-палитре
    if level == 0:  # пусто
        return QColor(255, 255, 255, 8)
    if level == 1:  # low
        return QColor(239, 68, 68, 45)
    if level == 2:
        return QColor(245, 158, 11, 55)
    if level == 3:
        return QColor(250, 204, 21, 60)
    if level == 4:
        return QColor(34, 197, 94, 55)
    return QColor(34, 197, 94, 95)  # 100%+


class LoadPage(QWidget):
    """
    Загрузка (неделя): ресурсы x дни, в клетке %.
    Клик по клетке -> callback open_schedule(org_id, day)
    """

    def __init__(self, user: AuthUser, open_schedule_cb, parent=None):
        super().__init__(parent)
        self.user = user
        self._open_schedule = open_schedule_cb  # callable(org_id:int, day:date)

        self._settings = QSettings("SportApp", "Load")

        self.lbl_title = QLabel("Загрузка (неделя)")
        self.lbl_title.setObjectName("sectionTitle")

        self.cmb_org = QComboBox()
        self.cmb_org.currentIndexChanged.connect(self.reload)

        self.dt_anchor = QDateEdit()
        self.dt_anchor.setCalendarPopup(True)
        self.dt_anchor.setDate(date.today())
        self.dt_anchor.setDisplayFormat("dd.MM.yyyy")
        self.dt_anchor.setFixedWidth(130)
        self.dt_anchor.dateChanged.connect(lambda *_: self.reload())

        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.btn_prev.setFixedWidth(36)
        self.btn_next.setFixedWidth(36)
        self.btn_prev.clicked.connect(lambda: self._shift_week(-7))
        self.btn_next.clicked.connect(lambda: self._shift_week(+7))

        self.cb_cancelled = QCheckBox("Отменённые")
        self.cb_cancelled.setChecked(False)
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())

        self.lbl_range = QLabel("—")
        self.lbl_range.setStyleSheet("color: rgba(226,232,240,0.6); font-weight: 600;")

        # таблица
        self.tbl = QTableWidget()
        self.tbl.setObjectName("loadHeatmap")
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.itemClicked.connect(self._on_cell_clicked)

        header = self.tbl.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        # top bar
        top = QHBoxLayout()
        top.setContentsMargins(12, 12, 12, 8)
        top.setSpacing(10)
        top.addWidget(self.lbl_title)
        top.addWidget(QLabel("Учреждение:"))
        top.addWidget(self.cmb_org, 1)
        top.addWidget(QLabel("Неделя:"))
        top.addWidget(self.btn_prev)
        top.addWidget(self.dt_anchor)
        top.addWidget(self.btn_next)
        top.addSpacing(10)
        top.addWidget(self.cb_cancelled)
        top.addStretch(1)
        top.addWidget(self.lbl_range)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        QTimer.singleShot(0, self._load_refs)

        # базовый стиль (можно вынести в общий qss)
        self.setStyleSheet("""
            QWidget#page { background: #0b1220; }
            QTableWidget#loadHeatmap {
                background: #0b1220;
                border: 1px solid rgba(255,255,255,0.08);
                gridline-color: rgba(255,255,255,0.08);
                color: rgba(226,232,240,0.9);
                selection-background-color: rgba(99,102,241,0.25);
            }
            QHeaderView::section {
                background: #0f172a;
                color: rgba(226,232,240,0.65);
                border: none;
                padding: 8px 6px;
                font-weight: 800;
                font-size: 11px;
                text-transform: uppercase;
            }
        """)

    def _shift_week(self, delta_days: int) -> None:
        d = self.dt_anchor.date().toPython()
        self.dt_anchor.setDate(d + timedelta(days=delta_days))

    def _load_refs(self) -> None:
        try:
            allowed_orgs = list_allowed_org_ids(int(self.user.id), str(self.user.role_code))
            orgs = list_active_orgs_by_ids(allowed_orgs)

            self.cmb_org.blockSignals(True)
            self.cmb_org.clear()
            for o in orgs:
                self.cmb_org.addItem(o.name, int(o.id))
            self.cmb_org.blockSignals(False)

            # restore last org (optional)
            last_org = self._settings.value("load/org_id", None)
            if last_org is not None:
                idx = self.cmb_org.findData(int(last_org))
                if idx >= 0:
                    self.cmb_org.setCurrentIndex(idx)

        except Exception as e:
            QMessageBox.critical(self, "Загрузка", f"Ошибка загрузки учреждений:\n{e}")
            return

        self.reload()

    def _current_org_id(self) -> Optional[int]:
        v = self.cmb_org.currentData()
        return int(v) if v is not None else None

    def reload(self) -> None:
        org_id = self._current_org_id()
        if org_id is None:
            return

        # права на просмотр (как минимум can_view)
        acc = get_org_access(int(self.user.id), str(self.user.role_code), int(org_id))
        if not bool(getattr(acc, "can_view", True)):
            QMessageBox.warning(self, "Доступ запрещён", "Нет доступа к учреждению.")
            return

        self._settings.setValue("load/org_id", int(org_id))

        anchor = self.dt_anchor.date().toPython()
        week_start, week_end = _week_range(anchor)
        self.lbl_range.setText(f"{week_start:%d.%m.%Y} – {week_end:%d.%m.%Y}")

        ws, we, _is24 = _load_org_work_window(int(org_id))
        cap_day = _sec_between(ws, we)

        resources = _load_resources_for_org(int(org_id))
        if not resources:
            self.tbl.setRowCount(0)
            self.tbl.setColumnCount(0)
            return

        start_dt = datetime.combine(week_start, time(0, 0), tzinfo=TZ)
        end_dt = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=TZ)

        include_cancelled = self.cb_cancelled.isChecked()
        bookings = _load_bookings_for_week(int(org_id), start_dt, end_dt, include_cancelled)

        # индекс ресурсов
        res_keys = {(r.venue_id, r.venue_unit_id) for r in resources}
        busy = defaultdict(int)  # (venue_id, unit_id, day)->sec

        for b in bookings:
            for i in range(7):
                d = week_start + timedelta(days=i)
                w0 = datetime.combine(d, ws, tzinfo=TZ)
                w1 = datetime.combine(d, we, tzinfo=TZ)
                sec = _overlap_seconds(b["starts_at"], b["ends_at"], w0, w1)
                if sec <= 0:
                    continue

                key = (int(b["venue_id"]), b["venue_unit_id"])
                if b["venue_unit_id"] is not None and key in res_keys:
                    busy[(int(b["venue_id"]), int(b["venue_unit_id"]), d)] += sec
                else:
                    if (int(b["venue_id"]), None) in res_keys:
                        busy[(int(b["venue_id"]), None, d)] += sec

        # строим таблицу
        days = [week_start + timedelta(days=i) for i in range(7)]
        weekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]

        self.tbl.blockSignals(True)
        self.tbl.clear()

        self.tbl.setRowCount(len(resources))
        self.tbl.setColumnCount(1 + 7)
        self.tbl.setHorizontalHeaderLabels(["Ресурс"] + [f"{weekdays[d.weekday()]}\n{d:%d.%m}" for d in days])

        # размеры
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        f_res = QFont()
        f_res.setPointSize(max(f_res.pointSize(), 10))
        f_pct = QFont()
        f_pct.setPointSize(max(f_pct.pointSize(), 10))
        f_pct.setBold(True)

        for r_idx, rsrc in enumerate(resources):
            it_res = QTableWidgetItem(rsrc.name)
            it_res.setForeground(TEXT)
            it_res.setBackground(QBrush(BG_CARD))
            it_res.setFont(f_res)
            it_res.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            it_res.setData(Qt.ItemDataRole.UserRole, ("resource", rsrc.venue_id, rsrc.venue_unit_id))
            self.tbl.setItem(r_idx, 0, it_res)

            for i, d in enumerate(days):
                sec = busy.get((rsrc.venue_id, rsrc.venue_unit_id, d), 0)
                pct = 0.0 if cap_day <= 0 else (100.0 * sec / cap_day)

                level = _heat_level(pct)
                col = _level_color(level)

                it = QTableWidgetItem(f"{pct:.0f}%")
                it.setFont(f_pct)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setForeground(QColor(255, 255, 255, 240) if level != 3 else QColor(0, 0, 0, 200))
                it.setBackground(QBrush(col))
                it.setData(Qt.ItemDataRole.UserRole, ("cell", int(org_id), rsrc.venue_id, rsrc.venue_unit_id, d))
                self.tbl.setItem(r_idx, 1 + i, it)

        self.tbl.resizeRowsToContents()
        self.tbl.blockSignals(False)

    def _on_cell_clicked(self, item: QTableWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or not isinstance(data, tuple):
            return
        if data[0] != "cell":
            return

        _tag, org_id, _venue_id, _unit_id, d = data
        try:
            self._open_schedule(int(org_id), d)
        except Exception as e:
            QMessageBox.critical(self, "Переход", f"Не удалось открыть расписание:\n{e}")
