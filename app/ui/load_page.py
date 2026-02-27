# app/ui/load_page.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from psycopg2.extras import RealDictCursor

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QDateEdit, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QStyledItemDelegate, QStyle,
    QLineEdit, QProgressBar, QScrollArea, QFrame,
)

from app.db import get_conn, put_conn
from app.services.users_service import AuthUser
from app.services.access_service import list_allowed_org_ids, get_org_access
from app.services.ref_service import list_active_orgs_by_ids, list_active_venues
from app.services.venue_units_service import list_venue_units
from app.services.venue_status_service import get_available_venue_ids_for_week
from app.ui.schedule_page import _style_calendar_widget


TZ = timezone(timedelta(hours=3))

BG_BASE = QColor("#0b1220")
BG_CARD = QColor("#0f172a")
BORDER   = QColor(255, 255, 255, 20)
TEXT     = QColor(226, 232, 240)
TEXT_DIM = QColor(226, 232, 240, 140)

WEEKDAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_org_work_window(org_id: int) -> tuple[time, time, bool]:
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT work_start, work_end, is_24h FROM public.sport_orgs WHERE id=%s",
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

def _load_bookings_for_week(
    org_id: int,
    start_dt: datetime,
    end_dt: datetime,
    include_cancelled: bool,
) -> list[dict]:
    cancel = "" if include_cancelled else "AND b.status <> 'cancelled'"
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT b.id, b.venue_id, b.venue_unit_id,
                       b.starts_at, b.ends_at, b.status
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


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resource:
    venue_id: int
    venue_unit_id: Optional[int]
    name: str
    venue_name: str


@dataclass
class FreeSlot:
    resource_name: str
    day: date
    start: time
    end: time
    venue_id: int
    venue_unit_id: Optional[int]

    @property
    def duration_min(self) -> int:
        s = datetime.combine(self.day, self.start)
        e = datetime.combine(self.day, self.end)
        return max(0, int((e - s).total_seconds()) // 60)

    @property
    def duration_str(self) -> str:
        m = self.duration_min
        if m >= 60:
            h, mm = divmod(m, 60)
            return f"{h}ч {mm}мин" if mm else f"{h}ч"
        return f"{m}мин"


def _week_range(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def _overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    s = max(a0, b0)
    e = min(a1, b1)
    return max(0, int((e - s).total_seconds()))


def _sec_between(t0: time, t1: time) -> int:
    return int(
        (
            datetime.combine(date.today(), t1)
            - datetime.combine(date.today(), t0)
        ).total_seconds()
    )


def _format_duration(seconds: int) -> str:
    h, rem = divmod(abs(seconds), 3600)
    m = rem // 60
    if h and m:
        return f"{h}ч {m}мин"
    if h:
        return f"{h}ч"
    return f"{m}мин"


def _load_resources_for_org(org_id: int) -> List[Resource]:
    venues = list_active_venues(org_id)
    out: List[Resource] = []
    for v in venues:
        units = list_venue_units(v.id, include_inactive=False)
        if units:
            units_sorted = sorted(
                units,
                key=lambda u: (int(getattr(u, "sort_order", 0)), str(u.name)),
            )
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


def _find_free_slots(
    resources: List[Resource],
    bookings: list[dict],
    days: List[date],
    ws: time,
    we: time,
    min_duration_min: int = 30,
) -> List[FreeSlot]:
    slots: List[FreeSlot] = []

    for rsrc in resources:
        for d in days:
            day_start = datetime.combine(d, ws, tzinfo=TZ)
            day_end   = datetime.combine(d, we, tzinfo=TZ)

            intervals: List[Tuple[datetime, datetime]] = []
            for b in bookings:
                vid = int(b["venue_id"])
                uid = b["venue_unit_id"]
                if rsrc.venue_unit_id is not None:
                    if vid != rsrc.venue_id or uid != rsrc.venue_unit_id:
                        continue
                else:
                    if vid != rsrc.venue_id:
                        continue
                bs = max(b["starts_at"], day_start)
                be = min(b["ends_at"],   day_end)
                if bs < be:
                    intervals.append((bs, be))

            intervals.sort()
            merged: List[Tuple[datetime, datetime]] = []
            for s, e in intervals:
                if merged and s <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))

            cursor = day_start
            for s, e in merged:
                if s > cursor:
                    gap_min = int((s - cursor).total_seconds()) // 60
                    if gap_min >= min_duration_min:
                        slots.append(FreeSlot(
                            resource_name=rsrc.name,
                            day=d,
                            start=cursor.timetz().replace(tzinfo=None),
                            end=s.timetz().replace(tzinfo=None),
                            venue_id=rsrc.venue_id,
                            venue_unit_id=rsrc.venue_unit_id,
                        ))
                cursor = max(cursor, e)

            if cursor < day_end:
                gap_min = int((day_end - cursor).total_seconds()) // 60
                if gap_min >= min_duration_min:
                    slots.append(FreeSlot(
                        resource_name=rsrc.name,
                        day=d,
                        start=cursor.timetz().replace(tzinfo=None),
                        end=we,
                        venue_id=rsrc.venue_id,
                        venue_unit_id=rsrc.venue_unit_id,
                    ))

    slots.sort(key=lambda s: (-s.duration_min, s.day, s.resource_name))
    return slots


# ---------------------------------------------------------------------------
# Heat-map helpers
# ---------------------------------------------------------------------------

def _heat_level(pct: float) -> int:
    if pct < 1:   return 0
    if pct < 26:  return 1
    if pct < 51:  return 2
    if pct < 76:  return 3
    if pct < 101: return 4
    return 5


def _level_color(level: int) -> QColor:
    if level == 0: return QColor(255, 255, 255,  8)
    if level == 1: return QColor(239,  68,  68, 45)
    if level == 2: return QColor(245, 158,  11, 55)
    if level == 3: return QColor(250, 204,  21, 60)
    if level == 4: return QColor( 34, 197,  94, 55)
    return             QColor( 34, 197,  94, 95)


_LEVEL_CSS = {
    0: "background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);",
    1: "background: rgba(239,68,68,0.18);   border: 1px solid rgba(239,68,68,0.35);",
    2: "background: rgba(245,158,11,0.22);  border: 1px solid rgba(245,158,11,0.40);",
    3: "background: rgba(250,204,21,0.24);  border: 1px solid rgba(250,204,21,0.45);",
    4: "background: rgba(34,197,94,0.22);   border: 1px solid rgba(34,197,94,0.40);",
    5: "background: rgba(34,197,94,0.38);   border: 1px solid rgba(34,197,94,0.55);",
}


# ---------------------------------------------------------------------------
# Delegate
# ---------------------------------------------------------------------------

class HeatmapCellDelegate(QStyledItemDelegate):
    ROLE_PCT = Qt.ItemDataRole.UserRole + 101

    def paint(self, painter: QPainter, option, index):
        if index.column() == 0:
            super().paint(painter, option, index)
            return

        pct = index.data(self.ROLE_PCT)
        try:
            pct_f = float(pct) if pct is not None else 0.0
        except Exception:
            pct_f = 0.0

        level = _heat_level(pct_f)
        bg    = _level_color(level)

        r = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.fillRect(r, bg)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(r, QColor(99, 102, 241, 55))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(r, QColor(255, 255, 255, 10))

        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.drawRect(r.adjusted(0, 0, -1, -1))

        txt = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.setPen(
            QColor(0, 0, 0, 200) if level == 3 else QColor(255, 255, 255, 240)
        )
        f = painter.font()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)

        painter.restore()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class LoadPage(QWidget):

    def __init__(self, user: AuthUser, open_schedule_cb, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

        self.user           = user
        self._open_schedule = open_schedule_cb
        self._settings      = QSettings("SportApp", "Load")

        self._last_resources: List[Resource] = []
        self._last_bookings:  list[dict]     = []
        self._last_days:      List[date]     = []
        self._last_ws:        time           = time(8, 0)
        self._last_we:        time           = time(22, 0)
        self._last_cap_day:   int            = 0
        self._last_busy:      Dict           = {}

        # ── top bar ──────────────────────────────────────────────────────────
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
        _style_calendar_widget(self.dt_anchor)

        self.btn_prev  = QPushButton("◀")
        self.btn_next  = QPushButton("▶")
        self.btn_prev.setFixedWidth(36)
        self.btn_next.setFixedWidth(36)
        self.btn_prev.clicked.connect(lambda: self._shift_week(-7))
        self.btn_next.clicked.connect(lambda: self._shift_week(+7))

        self.btn_today = QPushButton("Сегодня")
        self.btn_today.setFixedWidth(80)
        self.btn_today.clicked.connect(lambda: self.dt_anchor.setDate(date.today()))

        self.cb_cancelled = QCheckBox("Отменённые")
        self.cb_cancelled.setChecked(False)
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())

        self.lbl_range = QLabel("—")
        self.lbl_range.setStyleSheet(
            "color: rgba(226,232,240,0.6); font-weight: 700;"
        )

        # ── filter ───────────────────────────────────────────────────────────
        self.ed_filter = QLineEdit()
        self.ed_filter.setPlaceholderText("Фильтр ресурсов…")
        self.ed_filter.setClearButtonEnabled(True)
        self.ed_filter.setFixedWidth(220)
        self.ed_filter.textChanged.connect(self._apply_resource_filter)

        # ── KPI cards ────────────────────────────────────────────────────────
        self.kpi_avg_card      = self._make_kpi_card("Средняя загрузка")
        self.kpi_peak_day_card = self._make_kpi_card("Пик (день)")
        self.kpi_peak_res_card = self._make_kpi_card("Пик (ресурс)")
        self.kpi_hours_card    = self._make_kpi_card("Занято / Доступно")
        self.kpi_free_card     = self._make_kpi_card("Свободных окон")

        # ── legend ───────────────────────────────────────────────────────────
        legend_widget = self._build_legend()

        # ── heatmap table ────────────────────────────────────────────────────
        self.tbl = QTableWidget()
        self.tbl.setObjectName("loadHeatmap")
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setMouseTracking(True)
        self.tbl.itemClicked.connect(self._on_cell_clicked)

        self._cell_delegate = HeatmapCellDelegate(self.tbl)
        self.tbl.setItemDelegate(self._cell_delegate)

        hdr = self.tbl.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setStretchLastSection(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── free slots panel ─────────────────────────────────────────────────
        self.free_slots_container = QWidget()
        self.free_slots_layout    = QVBoxLayout(self.free_slots_container)
        self.free_slots_layout.setContentsMargins(0, 0, 0, 0)
        self.free_slots_layout.setSpacing(4)

        free_scroll = QScrollArea()
        free_scroll.setWidgetResizable(True)
        free_scroll.setWidget(self.free_slots_container)
        free_scroll.setFixedHeight(180)
        free_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self.lbl_free_title = QLabel("🔍 Свободные окна (от 30 мин)")
        self.lbl_free_title.setStyleSheet(
            "color: rgba(226,232,240,0.82); font-weight: 800;"
            " font-size: 13px; padding: 4px 0;"
        )

        # ── layouts ──────────────────────────────────────────────────────────
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
        top.addWidget(self.btn_today)
        top.addSpacing(10)
        top.addWidget(self.cb_cancelled)
        top.addStretch(1)
        top.addWidget(self.lbl_range)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(12, 0, 12, 0)
        filter_row.addWidget(self.ed_filter)
        filter_row.addStretch(1)
        filter_row.addWidget(legend_widget)

        kpi_row = QHBoxLayout()
        kpi_row.setContentsMargins(12, 0, 12, 0)
        kpi_row.setSpacing(12)
        kpi_row.addWidget(self.kpi_avg_card["widget"],      1)
        kpi_row.addWidget(self.kpi_peak_day_card["widget"], 1)
        kpi_row.addWidget(self.kpi_peak_res_card["widget"], 1)
        kpi_row.addWidget(self.kpi_hours_card["widget"],    1)
        kpi_row.addWidget(self.kpi_free_card["widget"],     1)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)
        root.addLayout(top)
        root.addLayout(kpi_row)
        root.addLayout(filter_row)
        root.addWidget(self.tbl, 3)
        root.addWidget(self.lbl_free_title)
        root.addWidget(free_scroll, 1)

        QTimer.singleShot(0, self._load_refs)

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

    # ── KPI card ─────────────────────────────────────────────────────────────

    def _make_kpi_card(self, title: str) -> dict:
        w = QFrame()
        w.setStyleSheet("""
            QFrame {
                background: rgba(15,23,42,0.45);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
            }
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(
            "color: rgba(226,232,240,0.55); font-weight: 800;"
            " font-size: 11px; border: none; background: transparent;"
        )
        lbl_v = QLabel("—")
        lbl_v.setStyleSheet(
            "color: rgba(226,232,240,0.95); font-weight: 900;"
            " font-size: 18px; border: none; background: transparent;"
        )
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255,255,255,0.06);
                border: none; border-radius: 3px;
            }
            QProgressBar::chunk {
                background: rgba(99,102,241,0.75);
                border-radius: 3px;
            }
        """)
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        lay.addWidget(bar)
        return {"widget": w, "title": lbl_t, "value": lbl_v, "bar": bar}

    def _update_kpi(self, card: dict, value: str,
                    pct: float = 0.0, bar_color: str = "") -> None:
        card["value"].setText(value)
        card["bar"].setValue(min(100, max(0, int(pct))))
        if bar_color:
            card["bar"].setStyleSheet(f"""
                QProgressBar {{
                    background: rgba(255,255,255,0.06);
                    border: none; border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background: {bar_color};
                    border-radius: 3px;
                }}
            """)

    # ── legend ───────────────────────────────────────────────────────────────

    def _build_legend(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        labels = ["0%", "1–25%", "26–50%", "51–75%", "76–100%", "100%+"]
        for i, txt in enumerate(labels):
            sq = QLabel()
            sq.setFixedSize(14, 14)
            sq.setStyleSheet(f"border-radius: 4px; {_LEVEL_CSS.get(i, '')}")
            lbl = QLabel(txt)
            lbl.setStyleSheet(
                "color: rgba(226,232,240,0.50); font-size: 11px; font-weight: 700;"
            )
            lay.addWidget(sq)
            lay.addWidget(lbl)
        return w

    # ── free-slot card ───────────────────────────────────────────────────────

    def _make_free_slot_widget(self, slot: FreeSlot, org_id: int) -> QWidget:
        w = QFrame()
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        w.setStyleSheet("""
            QFrame {
                background: rgba(34,197,94,0.08);
                border: 1px solid rgba(34,197,94,0.25);
                border-radius: 10px;
            }
            QFrame:hover {
                background: rgba(34,197,94,0.15);
                border-color: rgba(34,197,94,0.45);
            }
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(12)

        day_str  = f"{WEEKDAYS_RU[slot.day.weekday()]} {slot.day:%d.%m}"
        time_str = f"{slot.start:%H:%M}–{slot.end:%H:%M}"

        def _lbl(text, style):
            l = QLabel(text)
            l.setStyleSheet(style + " border: none; background: transparent;")
            return l

        lay.addWidget(_lbl(slot.resource_name,
            "color: rgba(226,232,240,0.90); font-weight: 700; font-size: 12px;"), 2)
        lay.addWidget(_lbl(day_str,
            "color: rgba(226,232,240,0.70); font-weight: 600; font-size: 12px;"), 1)
        lay.addWidget(_lbl(time_str,
            "color: rgba(34,197,94,0.95);   font-weight: 800; font-size: 12px;"), 1)
        lay.addWidget(_lbl(slot.duration_str,
            "color: rgba(226,232,240,0.55); font-weight: 600; font-size: 11px;"), 1)

        w.mousePressEvent = lambda ev: self._open_schedule(int(org_id), slot.day)
        return w

    # ── navigation ───────────────────────────────────────────────────────────

    def _shift_week(self, delta_days: int) -> None:
        d = self.dt_anchor.date().toPython()
        self.dt_anchor.setDate(d + timedelta(days=delta_days))

    # ── refs ─────────────────────────────────────────────────────────────────

    def _load_refs(self) -> None:
        try:
            allowed_orgs = list_allowed_org_ids(
                int(self.user.id), str(self.user.role_code)
            )
            orgs = list_active_orgs_by_ids(allowed_orgs)

            self.cmb_org.blockSignals(True)
            self.cmb_org.clear()
            for o in orgs:
                self.cmb_org.addItem(o.name, int(o.id))
            self.cmb_org.blockSignals(False)

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

    # ── filter ───────────────────────────────────────────────────────────────

    def _apply_resource_filter(self) -> None:
        q = (self.ed_filter.text() or "").strip().lower()
        for r in range(self.tbl.rowCount()):
            item = self.tbl.item(r, 0)
            if not item:
                continue
            name = (item.text() or "").lower()
            self.tbl.setRowHidden(r, bool(q) and q not in name)

    # ── main reload ──────────────────────────────────────────────────────────

    def reload(self) -> None:
        org_id = self._current_org_id()
        if org_id is None:
            return

        acc = get_org_access(
            int(self.user.id), str(self.user.role_code), int(org_id)
        )
        if not bool(getattr(acc, "can_view", True)):
            QMessageBox.warning(self, "Доступ запрещён", "Нет доступа к учреждению.")
            return

        self._settings.setValue("load/org_id", int(org_id))

        anchor     = self.dt_anchor.date().toPython()
        week_start, week_end = _week_range(anchor)
        self.lbl_range.setText(f"{week_start:%d.%m.%Y} – {week_end:%d.%m.%Y}")

        ws, we, _is24 = _load_org_work_window(int(org_id))
        cap_day = _sec_between(ws, we)

        # Все ресурсы учреждения
        all_resources = _load_resources_for_org(int(org_id))

        if not all_resources:
            self._reset_empty()
            return

        days = [week_start + timedelta(days=i) for i in range(7)]

        # ── Фильтрация: убираем площадки закрытые/вне сезона всю неделю ──
        all_venue_ids = list({r.venue_id for r in all_resources})
        try:
            available_venue_ids = get_available_venue_ids_for_week(
                all_venue_ids, week_start, week_end
            )
        except Exception:
            # Если запрос упал — показываем всё, чтобы не сломать страницу
            available_venue_ids = set(all_venue_ids)

        resources = [r for r in all_resources if r.venue_id in available_venue_ids]

        if not resources:
            self._reset_empty()
            return

        # ── Бронирования ─────────────────────────────────────────────────────
        start_dt = datetime.combine(week_start, time(0, 0), tzinfo=TZ)
        end_dt   = datetime.combine(week_end + timedelta(days=1), time(0, 0), tzinfo=TZ)

        include_cancelled = self.cb_cancelled.isChecked()
        bookings = _load_bookings_for_week(
            int(org_id), start_dt, end_dt, include_cancelled
        )

        self._last_resources = resources
        self._last_bookings  = bookings
        self._last_days      = days
        self._last_ws        = ws
        self._last_we        = we
        self._last_cap_day   = cap_day

        # ── Подсчёт занятости ────────────────────────────────────────────────
        res_keys = {(r.venue_id, r.venue_unit_id) for r in resources}
        busy: Dict = defaultdict(int)

        for b in bookings:
            for i in range(7):
                d  = week_start + timedelta(days=i)
                w0 = datetime.combine(d, ws, tzinfo=TZ)
                w1 = datetime.combine(d, we, tzinfo=TZ)
                sec = _overlap_seconds(b["starts_at"], b["ends_at"], w0, w1)
                if sec <= 0:
                    continue
                key = (int(b["venue_id"]), b["venue_unit_id"])
                if b["venue_unit_id"] is not None and key in res_keys:
                    busy[(int(b["venue_id"]), int(b["venue_unit_id"]), d)] += sec
                elif (int(b["venue_id"]), None) in res_keys:
                    busy[(int(b["venue_id"]), None, d)] += sec

        self._last_busy = busy

        # ── KPI ──────────────────────────────────────────────────────────────
        total_busy = 0
        total_cap  = cap_day * 7 * len(resources)

        day_busy: Dict[date, int] = {d: 0 for d in days}
        res_busy: Dict[str, int]  = {}

        for rsrc in resources:
            rb = 0
            for d in days:
                sec = busy.get((rsrc.venue_id, rsrc.venue_unit_id, d), 0)
                total_busy   += sec
                day_busy[d]  += sec
                rb           += sec
            res_busy[rsrc.name] = rb

        avg_pct = (100.0 * total_busy / total_cap) if total_cap > 0 else 0.0

        best_day     = max(days, key=lambda d: day_busy.get(d, 0))
        best_day_cap = cap_day * len(resources)
        best_day_pct = (
            (100.0 * day_busy[best_day] / best_day_cap) if best_day_cap > 0 else 0.0
        )

        best_res     = max(resources, key=lambda r: res_busy.get(r.name, 0))
        best_res_cap = cap_day * 7
        best_res_pct = (
            (100.0 * res_busy[best_res.name] / best_res_cap)
            if best_res_cap > 0 else 0.0
        )

        busy_h = total_busy / 3600.0
        cap_h  = total_cap  / 3600.0

        if avg_pct < 25:
            avg_bar_color = "rgba(239,68,68,0.75)"
        elif avg_pct < 50:
            avg_bar_color = "rgba(245,158,11,0.75)"
        elif avg_pct < 75:
            avg_bar_color = "rgba(250,204,21,0.75)"
        else:
            avg_bar_color = "rgba(34,197,94,0.75)"

        self._update_kpi(self.kpi_avg_card,      f"{avg_pct:.1f}%",  avg_pct,      avg_bar_color)
        self._update_kpi(self.kpi_peak_day_card,
            f"{WEEKDAYS_RU[best_day.weekday()]} {best_day:%d.%m} ({best_day_pct:.0f}%)",
            best_day_pct, "rgba(99,102,241,0.75)")
        self._update_kpi(self.kpi_peak_res_card,
            f"{best_res.name[:25]}{'…' if len(best_res.name) > 25 else ''}"
            f" ({best_res_pct:.0f}%)",
            best_res_pct, "rgba(99,102,241,0.75)")
        self._update_kpi(self.kpi_hours_card,
            f"{busy_h:.1f}ч / {cap_h:.1f}ч",    avg_pct, avg_bar_color)

        # ── Free slots ───────────────────────────────────────────────────────
        free_slots = _find_free_slots(
            resources, bookings, days, ws, we, min_duration_min=30
        )
        self._update_kpi(self.kpi_free_card,
            str(len(free_slots)),
            min(100, len(free_slots) * 3),
            "rgba(34,197,94,0.75)")
        self._render_free_slots(free_slots[:30], int(org_id))

        # ── Heatmap table ────────────────────────────────────────────────────
        self.tbl.blockSignals(True)
        self.tbl.clear()

        n_res = len(resources)
        self.tbl.setRowCount(n_res + 1)       # +1 строка «ИТОГО»
        self.tbl.setColumnCount(1 + 7 + 1)    # ресурс + 7 дней + итого

        self.tbl.setHorizontalHeaderLabels(
            ["Ресурс"]
            + [f"{WEEKDAYS_RU[d.weekday()]}\n{d:%d.%m}" for d in days]
            + ["Итого"]
        )

        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 9):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.tbl.setColumnWidth(c, 78)

        f_res = QFont()
        f_res.setPointSize(max(f_res.pointSize(), 10))

        f_pct = QFont()
        f_pct.setPointSize(max(f_pct.pointSize(), 10))
        f_pct.setBold(True)

        for r_idx, rsrc in enumerate(resources):
            # Колонка 0 — название ресурса
            it_res = QTableWidgetItem(rsrc.name)
            it_res.setForeground(TEXT)
            it_res.setBackground(QBrush(BG_CARD))
            it_res.setFont(f_res)
            it_res.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            it_res.setData(
                Qt.ItemDataRole.UserRole,
                ("resource", rsrc.venue_id, rsrc.venue_unit_id),
            )
            self.tbl.setItem(r_idx, 0, it_res)

            row_total_sec = 0
            for i, d in enumerate(days):
                sec      = busy.get((rsrc.venue_id, rsrc.venue_unit_id, d), 0)
                row_total_sec += sec
                pct      = 0.0 if cap_day <= 0 else (100.0 * sec / cap_day)
                level    = _heat_level(pct)
                free_sec = max(0, cap_day - sec)

                it = QTableWidgetItem(f"{pct:.0f}%")
                it.setFont(f_pct)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setData(HeatmapCellDelegate.ROLE_PCT, float(pct))
                it.setForeground(
                    QColor(0, 0, 0, 200) if level == 3
                    else QColor(255, 255, 255, 240)
                )
                it.setToolTip(
                    f"{rsrc.name}\n"
                    f"{WEEKDAYS_RU[d.weekday()]} {d:%d.%m.%Y}\n"
                    f"Занято: {_format_duration(sec)}\n"
                    f"Свободно: {_format_duration(free_sec)}\n"
                    f"Загрузка: {pct:.1f}%"
                )
                it.setData(
                    Qt.ItemDataRole.UserRole,
                    ("cell", int(org_id), rsrc.venue_id, rsrc.venue_unit_id, d),
                )
                self.tbl.setItem(r_idx, 1 + i, it)

            # Итого по строке
            row_cap   = cap_day * 7
            row_pct   = (100.0 * row_total_sec / row_cap) if row_cap > 0 else 0.0
            row_level = _heat_level(row_pct)

            it_total = QTableWidgetItem(f"{row_pct:.0f}%")
            it_total.setFont(f_pct)
            it_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_total.setData(HeatmapCellDelegate.ROLE_PCT, float(row_pct))
            it_total.setForeground(
                QColor(0, 0, 0, 200) if row_level == 3
                else QColor(255, 255, 255, 240)
            )
            it_total.setToolTip(
                f"{rsrc.name} — неделя\n"
                f"Занято: {_format_duration(row_total_sec)}\n"
                f"Загрузка: {row_pct:.1f}%"
            )
            self.tbl.setItem(r_idx, 8, it_total)

        # ── Строка «ИТОГО» ───────────────────────────────────────────────────
        it_lbl = QTableWidgetItem("ИТОГО")
        it_lbl.setFont(f_pct)
        it_lbl.setForeground(TEXT)
        it_lbl.setBackground(QBrush(QColor(15, 23, 42, 180)))
        it_lbl.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.tbl.setItem(n_res, 0, it_lbl)

        week_total_sec = 0
        col_cap        = cap_day * len(resources)

        for i, d in enumerate(days):
            col_sec       = day_busy.get(d, 0)
            week_total_sec += col_sec
            col_pct       = (100.0 * col_sec / col_cap) if col_cap > 0 else 0.0
            col_level     = _heat_level(col_pct)

            it_col = QTableWidgetItem(f"{col_pct:.0f}%")
            it_col.setFont(f_pct)
            it_col.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_col.setData(HeatmapCellDelegate.ROLE_PCT, float(col_pct))
            it_col.setForeground(
                QColor(0, 0, 0, 200) if col_level == 3
                else QColor(255, 255, 255, 240)
            )
            it_col.setToolTip(
                f"{WEEKDAYS_RU[d.weekday()]} {d:%d.%m} — все ресурсы\n"
                f"Занято: {_format_duration(col_sec)}\n"
                f"Загрузка: {col_pct:.1f}%"
            )
            it_col.setData(
                Qt.ItemDataRole.UserRole,
                ("cell", int(org_id), 0, None, d),
            )
            self.tbl.setItem(n_res, 1 + i, it_col)

        # Правый нижний угол — grand total
        grand_pct   = (100.0 * week_total_sec / total_cap) if total_cap > 0 else 0.0
        grand_level = _heat_level(grand_pct)

        it_grand = QTableWidgetItem(f"{grand_pct:.0f}%")
        it_grand.setFont(f_pct)
        it_grand.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        it_grand.setData(HeatmapCellDelegate.ROLE_PCT, float(grand_pct))
        it_grand.setForeground(
            QColor(0, 0, 0, 200) if grand_level == 3
            else QColor(255, 255, 255, 240)
        )
        it_grand.setToolTip(
            f"Вся неделя — все ресурсы\n"
            f"Занято: {_format_duration(week_total_sec)}\n"
            f"Загрузка: {grand_pct:.1f}%"
        )
        self.tbl.setItem(n_res, 8, it_grand)

        self.tbl.resizeRowsToContents()
        self.tbl.blockSignals(False)
        self._apply_resource_filter()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _reset_empty(self) -> None:
        """Сбрасывает таблицу и KPI когда нет доступных ресурсов."""
        self.tbl.setRowCount(0)
        self.tbl.setColumnCount(0)
        for card in (
            self.kpi_avg_card, self.kpi_peak_day_card,
            self.kpi_peak_res_card, self.kpi_hours_card,
            self.kpi_free_card,
        ):
            self._update_kpi(card, "—")
        self._clear_free_slots()

    def _clear_free_slots(self) -> None:
        while self.free_slots_layout.count():
            child = self.free_slots_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _render_free_slots(self, slots: List[FreeSlot], org_id: int) -> None:
        self._clear_free_slots()
        if not slots:
            lbl = QLabel("Нет свободных окон от 30 мин")
            lbl.setStyleSheet(
                "color: rgba(226,232,240,0.45); font-style: italic; padding: 12px;"
            )
            self.free_slots_layout.addWidget(lbl)
            return
        for slot in slots:
            self.free_slots_layout.addWidget(
                self._make_free_slot_widget(slot, org_id)
            )
        self.free_slots_layout.addStretch(1)

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
            QMessageBox.critical(
                self, "Переход", f"Не удалось открыть расписание:\n{e}"
            )
