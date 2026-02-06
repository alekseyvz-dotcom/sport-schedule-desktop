from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, List, Tuple, Optional
from psycopg2.extras import RealDictCursor
from app.db import get_conn, put_conn

import os
import tempfile
import traceback

from app.services.access_service import list_allowed_org_ids, get_org_access
from app.services.ref_service import list_active_orgs_by_ids
from app.services.users_service import AuthUser

from app.services.gz_service import list_active_gz_groups_for_booking

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QPainterPath, QBrush
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
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStackedWidget,
    QSplitter,
    QProgressBar,
    QButtonGroup,
    QToolButton,
)

def _load_org_work_window(org_id: int) -> tuple[time, time]:
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
                # fallback на старое поведение
                return time(8, 0), time(22, 0)

            if bool(row.get("is_24h")):
                # делаем сетку на сутки
                return time(0, 0), time(23, 59, 59)

            return row["work_start"], row["work_end"]
    finally:
        if conn:
            put_conn(conn)

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


from app.services.ref_service import list_active_venues, list_active_tenants
from app.services.venue_units_service import list_venue_units
from app.services.bookings_service import (
    list_bookings_for_day,
    list_bookings_for_range,
    create_booking,
    update_booking,
    cancel_booking,
)
from app.ui.booking_dialog import BookingDialog

from PySide6.QtCore import QRectF

from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QStyle

class BookingBlockDelegate(QStyledItemDelegate):
    """v8 — fillRect + скругления через маску + текст без clip."""

    ROLE_PART = Qt.ItemDataRole.UserRole + 1
    ROLE_ROWS = Qt.ItemDataRole.UserRole + 2

    PD_FILL    = QColor(30, 58, 95)
    PD_BORDER  = QColor(50, 90, 145)
    PD_BADGE   = QColor(59, 130, 246)

    GZ_FILL    = QColor(80, 56, 20)
    GZ_BORDER  = QColor(130, 95, 25)
    GZ_BADGE   = QColor(217, 119, 6)

    GZF_FILL   = QColor(95, 78, 30)
    GZF_BORDER = QColor(160, 135, 45)
    GZF_BADGE  = QColor(251, 191, 36)

    CAN_FILL   = QColor(40, 45, 55)
    CAN_BORDER = QColor(75, 85, 100)
    CAN_BADGE  = QColor(100, 116, 139)

    BG         = QColor(11, 18, 32)
    EMPTY      = QColor(15, 20, 32)
    GRID       = QColor(255, 255, 255, 12)
    RAD        = 10  # радиус скругления

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bf = QFont()
        self._bf.setPointSizeF(max(self._bf.pointSizeF(), 9.5))

    def _page(self):
        w = self.parent()
        while w is not None:
            if isinstance(w, SchedulePage):
                return w
            w = getattr(w, 'parent', lambda: None)()
        return None

    def _pal(self, bk):
        if not bk:
            return self.BG, self.BG, self.BG
        s = (getattr(bk, "status", "") or "").lower()
        if s == "cancelled":
            return self.CAN_FILL, self.CAN_BORDER, self.CAN_BADGE
        k = (getattr(bk, "kind", "") or getattr(bk, "activity", "") or "").upper()
        if k == "GZ":
            gid = getattr(bk, "gz_group_id", None)
            pg = self._page()
            if pg and gid is not None and pg._gz_group_is_free.get(int(gid), False):
                return self.GZF_FILL, self.GZF_BORDER, self.GZF_BADGE
            return self.GZ_FILL, self.GZ_BORDER, self.GZ_BADGE
        return self.PD_FILL, self.PD_BORDER, self.PD_BADGE

    def paint(self, painter: QPainter, option, index):
        if index.column() == 0:
            super().paint(painter, option, index)
            return

        r    = option.rect
        bk   = index.data(Qt.ItemDataRole.UserRole)
        part = index.data(self.ROLE_PART)

        painter.save()
        painter.setClipRect(r)
        painter.fillRect(r, self.BG)

        if not bk:
            painter.fillRect(r, self.EMPTY)
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(r, QColor(99, 102, 241, 45))
                painter.setPen(QPen(QColor(99, 102, 241, 120), 1))
                painter.drawRect(r.adjusted(0, 0, -1, -1))
            elif option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(r, QColor(255, 255, 255, 12))
            painter.setPen(QPen(self.GRID, 1))
            painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
            painter.drawLine(r.right(), r.top(), r.right(), r.bottom())
            painter.restore()
            return

        fill, bdr, badge = self._pal(bk)
        R = self.RAD
        mx = 2

        # ── 1. Заливаем ВЕСЬ rect цветом блока ──
        painter.fillRect(r, fill)

        # ── 2. Скругления — рисуем углы цветом фона ──
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.BG)

        if part in ("top", None):
            # Левый верхний угол: заливаем квадрат R×R, вырезаем дугу
            self._round_corner(painter, r.left() + mx, r.top(), R, "tl", fill)
            # Правый верхний угол
            self._round_corner(painter, r.right() - mx - R, r.top(), R, "tr", fill)

        if part in ("bottom", None):
            # Левый нижний
            self._round_corner(painter, r.left() + mx, r.bottom() - R, R, "bl", fill)
            # Правый нижний
            self._round_corner(painter, r.right() - mx - R, r.bottom() - R, R, "br", fill)

        # ── 3. Боковые рамки ──
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QPen(bdr, 1))
        painter.drawLine(r.left() + mx, r.top(), r.left() + mx, r.bottom())
        painter.drawLine(r.right() - mx, r.top(), r.right() - mx, r.bottom())

        # Верх/низ рамки
        if part in ("top", None):
            painter.drawLine(r.left() + mx + R, r.top(),
                             r.right() - mx - R, r.top())
        if part in ("bottom", None):
            painter.drawLine(r.left() + mx + R, r.bottom(),
                             r.right() - mx - R, r.bottom())

        # ── 4. Selection ──
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(r, QColor(255, 255, 255, 18))

        # ── 5. Контент ──
        if part in ("top", None):
            fh = self._block_h(index, r)
            # Снимаем clip чтобы текст мог рисоваться в middle-ячейках ниже
            painter.setClipping(False)
            self._labels(painter, bk, index,
                         QRectF(r.left() + mx, r.top(),
                                r.width() - mx * 2, fh),
                         badge)

        painter.restore()

    def _round_corner(self, painter: QPainter, x: float, y: float,
                      R: int, corner: str, fill: QColor):
        """
        Рисует скруглённый угол: заливаем квадрат R×R цветом фона,
        потом рисуем четверть круга цветом заливки блока.
        """
        rect = QRectF(x, y, R, R)

        # Заливаем квадрат фоном (убираем угол блока)
        painter.setBrush(self.BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(rect)

        # Рисуем четверть эллипса цветом блока
        painter.setBrush(fill)
        arc_rect = QRectF(0, 0, R * 2, R * 2)

        if corner == "tl":
            arc_rect.moveTo(x, y)
            painter.drawPie(arc_rect, 90 * 16, 90 * 16)
        elif corner == "tr":
            arc_rect.moveTo(x - R, y)
            painter.drawPie(arc_rect, 0 * 16, 90 * 16)
        elif corner == "bl":
            arc_rect.moveTo(x, y - R)
            painter.drawPie(arc_rect, 180 * 16, 90 * 16)
        elif corner == "br":
            arc_rect.moveTo(x - R, y - R)
            painter.drawPie(arc_rect, 270 * 16, 90 * 16)

    def _block_h(self, index, top_rect) -> float:
        rd = index.data(self.ROLE_ROWS)
        if not rd:
            return float(top_rect.height())
        r0, r1 = rd
        t = self.parent()
        if t is None:
            return float(top_rect.height())
        return float(sum(t.rowHeight(i) for i in range(r0, r1 + 1)))

    def _labels(self, painter: QPainter, bk, index,
                rf: QRectF, badge: QColor):
        kind   = (getattr(bk, "kind", "") or
                  getattr(bk, "activity", "") or "").upper()
        status = (getattr(bk, "status", "") or "").lower()

        raw = (index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
        parts = [l.strip() for l in raw.split("\n") if l.strip()]
        name  = parts[0] if parts else ""
        event = parts[1] if len(parts) > 1 else ""

        if not event:
            sa = getattr(bk, "starts_at", None)
            ea = getattr(bk, "ends_at", None)
            if sa and ea:
                event = f"{sa:%H:%M} – {ea:%H:%M}"

        # ── Бейдж типа ──
        tag = ("ОТМ" if status == "cancelled"
               else "ПД" if kind == "PD"
               else "ГЗ" if kind == "GZ"
               else kind or "—")

        fb = QFont(self._bf)
        fb.setBold(True)
        painter.setFont(fb)
        fm = painter.fontMetrics()

        px = 7
        bw = fm.horizontalAdvance(tag) + px * 2
        bh = fm.height() + 4
        bx = rf.right() - bw - 6
        by = rf.top() + 6

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(badge)
        painter.drawRoundedRect(QRectF(bx, by, bw, bh), 5, 5)

        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(QRectF(bx, by, bw, bh),
                         Qt.AlignmentFlag.AlignCenter, tag)

        # ── Имя ──
        nl = rf.left() + 8
        nw = bx - 8 - nl
        if nw < 20:
            return

        fn = QFont(self._bf)
        fn.setBold(True)
        painter.setFont(fn)
        fmn = painter.fontMetrics()

        painter.setPen(QColor(255, 255, 255, 235))
        el = fmn.elidedText(name, Qt.TextElideMode.ElideRight, int(nw))
        painter.drawText(
            QRectF(nl, by, nw, bh),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            el)

        # ── Вторая строка (событие / время) ──
        if not event:
            return

        fs = QFont(self._bf)
        fs.setBold(False)
        fs.setPointSizeF(max(self._bf.pointSizeF() - 0.5, 8.5))
        painter.setFont(fs)
        fms = painter.fontMetrics()

        ey = by + bh + 3
        ew = rf.width() - 16
        eh = fms.height() + 4

        if ey + eh > rf.bottom() - 2 or ew < 30:
            return

        painter.setPen(QColor(255, 255, 255, 160))
        el_ev = fms.elidedText(event, Qt.TextElideMode.ElideRight, int(ew))
        painter.drawText(
            QRectF(rf.left() + 8, ey, ew, eh),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            el_ev)

    def sizeHint(self, option, index):
        return super().sizeHint(option, index)

class SchedulePage(QWidget):
    SLOT_MINUTES = 30

    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    LIST_ROLE_BOOKING = Qt.ItemDataRole.UserRole + 10

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.user = user
        
        self._gz_group_is_free: Dict[int, bool] = {}

        self._gz_groups: List[Dict] = []

        self._settings = QSettings("SportApp", "Schedule")

        self._work_start: time = time(8, 0)
        self._work_end: time = time(22, 0)

        self._resources: List[Resource] = []
        self._tenants: List[Dict] = []

        self.lbl_title = QLabel("Расписание")
        self.lbl_title.setObjectName("sectionTitle")

        self.cmb_org = QComboBox()
        self.cmb_org.currentIndexChanged.connect(self._on_org_changed)

        self.dt_day = QDateEdit()
        self.dt_day.setCalendarPopup(True)
        self.dt_day.setDate(date.today())
        self.dt_day.setDisplayFormat("dd.MM.yyyy")
        self.dt_day.setFixedWidth(130)
        self.dt_day.dateChanged.connect(lambda *_: self.reload())

        # --- intuitive view switch: tabs instead of "Вид:" combobox
        self.btn_view_grid = QToolButton()
        self.btn_view_grid.setObjectName("viewTab")
        self.btn_view_grid.setText("Слоты")
        self.btn_view_grid.setCheckable(True)

        self.btn_view_list = QToolButton()
        self.btn_view_list.setObjectName("viewTab")
        self.btn_view_list.setText("Список")
        self.btn_view_list.setCheckable(True)

        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_group.addButton(self.btn_view_grid)
        self._view_group.addButton(self.btn_view_list)
        self.btn_view_grid.clicked.connect(lambda: self._set_mode("grid"))
        self.btn_view_list.clicked.connect(lambda: self._set_mode("list"))

        # list-only controls
        self.cmb_period = QComboBox()
        self.cmb_period.addItem("День", "day")
        self.cmb_period.addItem("Неделя (Пн–Вс)", "week")
        self.cmb_period.addItem("Месяц", "month")
        self.cmb_period.addItem("Квартал", "quarter")
        self.cmb_period.addItem("Год", "year")
        self.cmb_period.currentIndexChanged.connect(lambda *_: self.reload())

        self.cb_cancelled = QCheckBox("Отменённые")
        self.cb_cancelled.setChecked(False)
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())

        self.btn_create = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_cancel = QPushButton("Отменить")
        self.btn_refresh = QPushButton("Обновить")
        self.btn_columns = QPushButton("Колонки…")

        self.btn_create.clicked.connect(self._on_create)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_columns.clicked.connect(self._on_columns)

        top = QHBoxLayout()
        top.setContentsMargins(12, 12, 12, 8)
        top.setSpacing(10)
        top.addWidget(self.lbl_title)
        top.addWidget(QLabel("Учреждение:"))
        top.addWidget(self.cmb_org, 1)
        top.addWidget(QLabel("Дата:"))
        top.addWidget(self.dt_day)

        # tabs
        top.addSpacing(6)
        top.addWidget(self.btn_view_grid)
        top.addWidget(self.btn_view_list)

        # list-only controls (will be hidden in grid mode)
        self.lbl_period_caption = QLabel("Период:")
        top.addWidget(self.lbl_period_caption)
        top.addWidget(self.cmb_period)

        top.addWidget(self.cb_cancelled)
        top.addWidget(self.btn_create)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_cancel)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_columns)

        # meta line (ONLY for list mode)
        self.meta_row = QWidget(self)
        meta_lay = QHBoxLayout(self.meta_row)
        meta_lay.setContentsMargins(12, 0, 12, 0)

        self.lbl_period = QLabel("")
        self.lbl_period.setObjectName("scheduleMeta")

        self.lbl_total = QLabel("")
        self.lbl_total.setObjectName("scheduleMetaStrong")

        meta_lay.addWidget(self.lbl_period, 1)
        meta_lay.addWidget(self.lbl_total, 0, Qt.AlignmentFlag.AlignRight)

        # --- GRID ---
        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setShowGrid(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.itemDoubleClicked.connect(lambda *_: self._on_edit())
        self.tbl.setObjectName("scheduleGrid")

        header = self.tbl.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Делегаты: общий = BookingBlockDelegate, колонка 0 = стандартный
        self._booking_delegate = BookingBlockDelegate(self.tbl)
        self.tbl.setItemDelegate(self._booking_delegate)
        self.tbl.setItemDelegateForColumn(0, QStyledItemDelegate(self.tbl))

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        # --- LIST + details
        self.tbl_list = QTableWidget()
        self.tbl_list.setObjectName("scheduleList")
        self._setup_list_table()

        self.details = self._make_details_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.tbl_list)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # stack
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tbl)      # 0
        self.stack.addWidget(splitter)      # 1

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.meta_row)
        root.addWidget(self.stack, 1)

        QTimer.singleShot(0, self._load_refs)

        # restore last mode (so "кликаю на вкладку расписание" -> открывает последний выбранный вид)
        last_mode = str(self._settings.value("schedule/view_mode", "grid"))
        self._set_mode(last_mode, persist=False)
    # -------- mode handling (fixes your issues) --------

    def showEvent(self, e):
        # if page is shown again, keep last selected mode
        super().showEvent(e)
        last_mode = str(self._settings.value("schedule/view_mode", "grid"))
        self._set_mode(last_mode, persist=False)

    def _set_mode(self, mode: str, *, persist: bool = True) -> None:
        mode = "list" if mode == "list" else "grid"
        if persist:
            self._settings.setValue("schedule/view_mode", mode)
    
        self.stack.setCurrentIndex(0 if mode == "grid" else 1)
    
        self.btn_view_grid.blockSignals(True)
        self.btn_view_list.blockSignals(True)
        self.btn_view_grid.setChecked(mode == "grid")
        self.btn_view_list.setChecked(mode == "list")
        self.btn_view_grid.blockSignals(False)
        self.btn_view_list.blockSignals(False)
    
        is_list = (mode == "list")
        self.cmb_period.setVisible(is_list)
        self.lbl_period_caption.setVisible(is_list)
        self.meta_row.setVisible(is_list)
    
        if not is_list:
            self.lbl_period.setText("")
            self.lbl_total.setText("")
    
        self.btn_columns.setEnabled(mode == "grid")
    
        # важно: учесть права на выбранное учреждение
        self._apply_access_buttons()
    
        self.reload()

    def _mode(self) -> str:
        return "list" if self.btn_view_list.isChecked() else "grid"

    def _apply_access_buttons(self) -> None:
        org_id = self.cmb_org.currentData()
        if org_id is None:
            self.btn_create.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            return
    
        acc = get_org_access(int(self.user.id), str(self.user.role_code), int(org_id))
        can_edit = bool(acc.can_edit)
    
        self.btn_create.setEnabled(can_edit and self._mode() == "grid")
        self.btn_edit.setEnabled(can_edit)
        self.btn_cancel.setEnabled(can_edit)

    # -------- details panel and list setup (same approach as before) --------

    def _make_kpi(self, title: str):
        t = QLabel(title)
        t.setObjectName("kpiTitle")
        v = QLabel("—")
        v.setObjectName("kpiValue")
        return t, v

    def _make_details_panel(self) -> QWidget:
        w = QWidget(self)

        w.setObjectName("detailsCard")

        self.lbl_d_title = QLabel("Детали брони")
        self.lbl_d_title.setObjectName("detailsTitle")

        self.lbl_d_main = QLabel("Выберите строку слева")
        self.lbl_d_main.setWordWrap(True)
        self.lbl_d_main.setObjectName("detailsText")

        self.lbl_d_extra = QLabel("")
        self.lbl_d_extra.setWordWrap(True)
        self.lbl_d_extra.setObjectName("detailsText")

        k1t, self.kpi_total = self._make_kpi("Итого бронирований")
        k2t, self.kpi_pd = self._make_kpi("ПД")
        k3t, self.kpi_gz = self._make_kpi("ГЗ")
        k4t, self.kpi_cancelled = self._make_kpi("Отменённые")

        kpi = QHBoxLayout()
        kpi.setContentsMargins(12, 8, 12, 8)
        for t, v in ((k1t, self.kpi_total), (k2t, self.kpi_pd), (k3t, self.kpi_gz), (k4t, self.kpi_cancelled)):
            box = QVBoxLayout()
            box.addWidget(t)
            box.addWidget(v)
            kpi.addLayout(box, 1)

        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.lbl_d_title)
        lay.addLayout(kpi)
        lay.addWidget(self.lbl_d_main)
        lay.addWidget(self.lbl_d_extra)
        lay.addStretch(1)
        return w

    def _setup_list_table(self) -> None:
        self.tbl_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_list.setAlternatingRowColors(False)
        self.tbl_list.setShowGrid(False)
        self.tbl_list.verticalHeader().setVisible(False)
        self.tbl_list.itemDoubleClicked.connect(lambda *_: self._on_edit())
        self.tbl_list.itemSelectionChanged.connect(self._update_details_from_selection)

        self.tbl_list.setColumnCount(7)
        self.tbl_list.setHorizontalHeaderLabels(["Дата", "Время", "Арендатор", "Событие", "Площадка", "Тип", "Статус"])

        header = self.tbl_list.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl_list.setFont(f)

    # -------- colors / text helpers --------
    _PD_COLOR = QColor(96, 165, 250)   # blue-400
    _GZ_COLOR = QColor(245, 158, 11)   # amber-500
    _CANCELLED_COLOR = QColor(148, 163, 184)  # slate-400 (нейтр)
    _EMPTY_SLOT_COLOR = QColor(0, 0, 0, 0)


    def _base_color_for_booking(self, b) -> QColor:
        if (getattr(b, "status", "") or "").lower() == "cancelled":
            return QColor(self._CANCELLED_COLOR)
    
        kind = (getattr(b, "kind", None) or getattr(b, "activity", "") or "").upper()
    
        if kind == "PD":
            return QColor(self._PD_COLOR)
    
        if kind == "GZ":
            base = QColor(self._GZ_COLOR)
            gz_group_id = getattr(b, "gz_group_id", None)
            if gz_group_id is not None and self._gz_group_is_free.get(int(gz_group_id), False):
                # на два тона светлее
                return self._lighten(base, steps=2, amount=120)
            return base
    
        return QColor("#e5e7eb")


    def _kind_title(self, kind: str) -> str:
        k = (kind or "").upper()
        return "ПД" if k == "PD" else ("ГЗ" if k == "GZ" else (k or "—"))

    def _status_title(self, status: str) -> str:
        s = (status or "").lower()
        if s == "planned":
            return "План"
        if s == "done":
            return "Проведено"
        if s == "cancelled":
            return "Отменено"
        return s or "—"

    def _status_color(self, status: str) -> QColor:
        s = (status or "").lower()
        if s == "cancelled":
            return QColor("#ef4444")
        if s == "done":
            return QColor("#64748b")
        return QColor("#0f172a")

    # -------- selection helpers --------

    def _selected_booking_from_grid(self):
        it = self.tbl.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _selected_booking_from_list(self):
        row = self.tbl_list.currentRow()
        if row < 0:
            return None
        it = self.tbl_list.item(row, 0)
        return it.data(self.LIST_ROLE_BOOKING) if it else None

    def _selected_booking(self):
        return self._selected_booking_from_list() if self._mode() == "list" else self._selected_booking_from_grid()

    def _row_to_datetime(self, day: date, row: int) -> datetime:
        slots = self._time_slots()
        row = max(0, min(row, len(slots) - 1))
        return datetime.combine(day, slots[row], tzinfo=self.TZ)
    
    
    def _selected_multi_units(self) -> Optional[Tuple[List[int], int, int]]:
        """
        Возвращает (cols, rmin, rmax) по выделению в сетке слотов.
        cols — индексы колонок таблицы self.tbl (>=1), rmin/rmax — строки.
        """
        ranges = self.tbl.selectedRanges()
        if not ranges:
            return None
    
        cols_set = set()
        rmin = 10**9
        rmax = -1
    
        for rg in ranges:
            rmin = min(rmin, rg.topRow())
            rmax = max(rmax, rg.bottomRow())
            for c in range(rg.leftColumn(), rg.rightColumn() + 1):
                if c <= 0:
                    continue
                cols_set.add(c)
    
        if not cols_set or rmax < rmin:
            return None
    
        return sorted(cols_set), rmin, rmax

    # -------- data loading / period --------

    def _load_refs(self):
        try:
            allowed_orgs = list_allowed_org_ids(int(self.user.id), str(self.user.role_code))
            orgs = list_active_orgs_by_ids(allowed_orgs)
    
            self.cmb_org.blockSignals(True)
            self.cmb_org.clear()
            for o in orgs:
                self.cmb_org.addItem(o.name, o.id)
            self.cmb_org.blockSignals(False)
    
            self._tenants = [{"id": t.id, "name": t.name} for t in list_active_tenants()]

        except Exception as e:
            _uilog("ERROR _load_refs: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(self, "Справочники", f"Ошибка загрузки справочников:\n{e}")
            return
    
        self._on_org_changed()

    def _on_org_changed(self):
        org_id = self.cmb_org.currentData()
    
        if org_id is None:
            self._gz_groups = []
            self.btn_create.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self._resources = []
            self._setup_table()
            self.tbl_list.setRowCount(0)
            self.reload()
            return
    
        org_id = int(org_id)

        # режим работы учреждения -> слоты
        try:
            self._work_start, self._work_end = _load_org_work_window(org_id)
        except Exception:
            # если что-то пошло не так — оставляем дефолт
            self._work_start, self._work_end = time(8, 0), time(22, 0)
        
        try:
            self._gz_groups = list_active_gz_groups_for_booking(org_id=org_id)
        except Exception:
            self._gz_groups = []
        
        # ожидаем, что list_active_gz_groups_for_booking вернёт ещё и is_free
        self._gz_group_is_free = {
            int(g["id"]): bool(g.get("is_free", False)) for g in (self._gz_groups or []) if g.get("id") is not None
        }
    
        acc = get_org_access(int(self.user.id), str(self.user.role_code), org_id)
        can_edit = bool(acc.can_edit)
    
        self.btn_create.setEnabled(can_edit and self._mode() == "grid")
        self.btn_edit.setEnabled(can_edit)
        self.btn_cancel.setEnabled(can_edit)
    
        try:
            venues = list_active_venues(org_id)
            resources: List[Resource] = []
    
            for v in venues:
                units = list_venue_units(v.id, include_inactive=False)
                if units:
                    units_sorted = sorted(units, key=lambda u: (int(getattr(u, "sort_order", 0)), str(u.name)))
                    for u in units_sorted:
                        resources.append(
                            Resource(
                                venue_id=v.id,
                                venue_name=v.name,
                                venue_unit_id=u.id,
                                resource_name=f"{v.name} — {u.name}",
                            )
                        )
                else:
                    resources.append(Resource(venue_id=v.id, venue_name=v.name, venue_unit_id=None, resource_name=v.name))
    
            resources.sort(key=lambda r: (r.venue_name, r.resource_name))
            self._resources = resources
            self._apply_order_and_hidden(org_id)
    
        except Exception as e:
            _uilog("ERROR _on_org_changed: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(self, "Площадки", f"Ошибка загрузки площадок:\n{e}")
            self._resources = []
    
        self._setup_table()
        self._apply_hidden_columns(org_id)
        self.reload()

    def _period_range(self, anchor: date) -> tuple[date, date]:
        p = self.cmb_period.currentData() or "day"
        if p == "day":
            return anchor, anchor
        if p == "week":
            start = anchor - timedelta(days=anchor.weekday())
            return start, start + timedelta(days=6)
        if p == "month":
            start = anchor.replace(day=1)
            next_m = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
            return start, next_m - timedelta(days=1)
        if p == "quarter":
            q = (anchor.month - 1) // 3
            start_m = q * 3 + 1
            start = anchor.replace(month=start_m, day=1)
            next_q = start.replace(year=start.year + 1, month=1) if start_m == 10 else start.replace(month=start_m + 3)
            return start, next_q - timedelta(days=1)
        if p == "year":
            return anchor.replace(month=1, day=1), anchor.replace(month=12, day=31)
        return anchor, anchor

    def _resolve_resource_name(self, venue_id: int, venue_unit_id) -> str:
        for r in self._resources:
            if int(r.venue_id) != int(venue_id):
                continue
            if r.venue_unit_id is None and venue_unit_id is None:
                return r.resource_name
            if r.venue_unit_id is not None and venue_unit_id is not None and int(r.venue_unit_id) == int(venue_unit_id):
                return r.resource_name
        if venue_unit_id is not None:
            return f"Площадка {venue_id} — зона {venue_unit_id}"
        return f"Площадка {venue_id}"

    def reload(self):
        if self._mode() == "list":
            return self._reload_list()
        return self._reload_grid()

    # -------- grid reload (same as before) --------

    def _time_slots(self) -> List[time]:
        out: List[time] = []
        cur = datetime.combine(date.today(), self._work_start)
        end = datetime.combine(date.today(), self._work_end)

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
            it.setForeground(QColor(226, 232, 240, 210))
            it.setBackground(QColor(15, 23, 42, 90))
            self.tbl.setItem(r, 0, it)

        for r in range(len(times)):
            for c in range(1, 1 + resource_count):
                it = QTableWidgetItem("")
                it.setData(Qt.ItemDataRole.UserRole, None)
                it.setData(BookingBlockDelegate.ROLE_PART, None)
                self.tbl.setItem(r, c, it)

        self.tbl.setColumnWidth(0, 70)
        self.tbl.resizeRowsToContents()

    def _reload_grid(self):
        self.meta_row.setVisible(False)

        # Очистка
        for r in range(self.tbl.rowCount()):
            for c in range(1, self.tbl.columnCount()):
                it = self.tbl.item(r, c)
                if it is None:
                    it = QTableWidgetItem("")
                    self.tbl.setItem(r, c, it)
                it.setText("")
                it.setData(Qt.ItemDataRole.UserRole, None)
                it.setData(BookingBlockDelegate.ROLE_PART, None)
                it.setData(BookingBlockDelegate.ROLE_ROWS, None)

        if not self._resources:
            return

        day = self.dt_day.date().toPython()
        include_cancelled = self.cb_cancelled.isChecked()
        venue_ids = sorted({rsrc.venue_id for rsrc in self._resources})

        try:
            bookings = list_bookings_for_day(venue_ids, day,
                                              include_cancelled=include_cancelled)
        except Exception as e:
            _uilog("ERROR list_bookings_for_day: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(self, "Расписание",
                                 f"Ошибка загрузки бронирований:\n{e}")
            return

        unit_col: Dict[int, int] = {}
        venue_fallback_col: Dict[int, int] = {}
        for i, rsrc in enumerate(self._resources):
            col = i + 1
            if rsrc.venue_unit_id is not None:
                unit_col[int(rsrc.venue_unit_id)] = col
            else:
                venue_fallback_col[int(rsrc.venue_id)] = col

        day_start = datetime.combine(day, self._work_start, tzinfo=self.TZ)
        day_end   = datetime.combine(day, self._work_end,   tzinfo=self.TZ)

        for b in bookings:
            col = None
            if getattr(b, "venue_unit_id", None) is not None:
                col = unit_col.get(int(b.venue_unit_id))
            if col is None:
                col = venue_fallback_col.get(int(b.venue_id))
            if not col:
                continue

            start = max(b.starts_at, day_start)
            end   = min(b.ends_at, day_end)
            if end <= start:
                continue

            r0 = int((start - day_start).total_seconds() //
                     (self.SLOT_MINUTES * 60))
            r1 = int(((end - day_start).total_seconds() - 1) //
                     (self.SLOT_MINUTES * 60))
            r0 = max(0, r0)
            r1 = min(self.tbl.rowCount() - 1, r1)

            span = r1 - r0

            for rr in range(r0, r1 + 1):
                it = self.tbl.item(rr, col)
                if it is None:
                    it = QTableWidgetItem("")
                    self.tbl.setItem(rr, col, it)

                it.setData(Qt.ItemDataRole.UserRole, b)
                it.setData(BookingBlockDelegate.ROLE_ROWS, (r0, r1))

                if span == 0:
                    it.setData(BookingBlockDelegate.ROLE_PART, None)
                elif rr == r0:
                    it.setData(BookingBlockDelegate.ROLE_PART, "top")
                elif rr == r1:
                    it.setData(BookingBlockDelegate.ROLE_PART, "bottom")
                else:
                    it.setData(BookingBlockDelegate.ROLE_PART, "middle")

            it0 = self.tbl.item(r0, col)
            if it0:
                kind = (getattr(b, "kind", "") or "").upper()
                tenant_name = (getattr(b, "tenant_name", "") or "").strip()
                if kind == "GZ":
                    tenant_name = (getattr(b, "gz_group_name", "") or "").strip()
                title = (getattr(b, "title", "") or "").strip()
                it0.setText(f"{tenant_name}\n{title}" if title else tenant_name)

        self.tbl.viewport().update()

    # -------- list reload --------

    def _reload_list(self):
        self.meta_row.setVisible(True)

        self.tbl_list.setRowCount(0)
        if not self._resources:
            self.lbl_period.setText("Период: —")
            self.lbl_total.setText("")
            self.kpi_total.setText("—")
            self.kpi_pd.setText("—")
            self.kpi_gz.setText("—")
            self.kpi_cancelled.setText("—")
            return

        anchor = self.dt_day.date().toPython()
        d0, d1 = self._period_range(anchor)
        self.lbl_period.setText(f"Период: {d0:%d.%m.%Y} – {d1:%d.%m.%Y}")

        start = datetime.combine(d0, time(0, 0), tzinfo=self.TZ)
        end = datetime.combine(d1 + timedelta(days=1), time(0, 0), tzinfo=self.TZ)

        include_cancelled = self.cb_cancelled.isChecked()
        venue_ids = sorted({rsrc.venue_id for rsrc in self._resources})

        try:
            bookings = list_bookings_for_range(venue_ids, start, end, include_cancelled=include_cancelled)
        except Exception as e:
            _uilog("ERROR list_bookings_for_range: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(self, "Расписание", f"Ошибка загрузки списка бронирований:\n{e}")
            return

        total = len(bookings)
        pd = sum(1 for b in bookings if (getattr(b, "kind", "") or "").upper() == "PD")
        gz = sum(1 for b in bookings if (getattr(b, "kind", "") or "").upper() == "GZ")
        canc = sum(1 for b in bookings if (getattr(b, "status", "") or "").lower() == "cancelled")

        self.kpi_total.setText(str(total))
        self.kpi_pd.setText(str(pd))
        self.kpi_gz.setText(str(gz))
        self.kpi_cancelled.setText(str(canc))

        busy_sec = 0
        for b in bookings:
            s = getattr(b, "starts_at", None)
            e = getattr(b, "ends_at", None)
            if s and e:
                busy_sec += int((e - s).total_seconds())
        busy_hours = round(busy_sec / 3600.0, 1)
        self.lbl_total.setText(f"Занято: {busy_hours} ч | Бронирований: {total}")

        bookings_sorted = sorted(bookings, key=lambda b: (getattr(b, "starts_at", datetime.min), getattr(b, "ends_at", datetime.min)))
        self.tbl_list.setRowCount(len(bookings_sorted))

        for row, b in enumerate(bookings_sorted):
            starts_at = getattr(b, "starts_at", None)
            ends_at = getattr(b, "ends_at", None)

            dt_str = starts_at.strftime("%d.%m.%Y") if starts_at else ""
            time_str = f"{starts_at:%H:%M}–{ends_at:%H:%M}" if starts_at and ends_at else ""
            kind_raw = (getattr(b, "kind", "") or "").upper()
            tenant = (getattr(b, "tenant_name", "") or "").strip()
            if kind_raw == "GZ":
                tenant = (getattr(b, "gz_group_name", "") or "").strip()
            title = (getattr(b, "title", "") or "").strip()

            venue_id = int(getattr(b, "venue_id", 0) or 0)
            unit_id = getattr(b, "venue_unit_id", None)
            resource_name = self._resolve_resource_name(venue_id, unit_id)

            kind = self._kind_title(getattr(b, "kind", ""))
            status = self._status_title(getattr(b, "status", ""))

            it0 = QTableWidgetItem(dt_str)
            it1 = QTableWidgetItem(time_str)
            it2 = QTableWidgetItem(tenant)
            it3 = QTableWidgetItem(title)
            it4 = QTableWidgetItem(resource_name)
            it5 = QTableWidgetItem(kind)
            it6 = QTableWidgetItem(status)

            it0.setData(self.LIST_ROLE_BOOKING, b)

            base = self._base_color_for_booking(b)
            for it in (it0, it1, it2, it3, it4, it5, it6):
                it.setData(Qt.ItemDataRole.BackgroundRole, base)
                it.setData(Qt.ItemDataRole.ForegroundRole, QColor(255, 255, 255, 230))

            for it in (it1, it5, it6):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it6.setData(Qt.ItemDataRole.ForegroundRole, self._status_color(getattr(b, "status", "")))

            self.tbl_list.setItem(row, 0, it0)
            self.tbl_list.setItem(row, 1, it1)
            self.tbl_list.setItem(row, 2, it2)
            self.tbl_list.setItem(row, 3, it3)
            self.tbl_list.setItem(row, 4, it4)
            self.tbl_list.setItem(row, 5, it5)
            self.tbl_list.setItem(row, 6, it6)

        self.tbl_list.resizeRowsToContents()

        if self.tbl_list.rowCount() > 0:
            self.tbl_list.setCurrentCell(0, 0)
            self._update_details_from_selection()

    def _update_details_from_selection(self):
        b = self._selected_booking_from_list()
        if not b:
            self.lbl_d_main.setText("Выберите строку слева")
            self.lbl_d_extra.setText("")
            return

        kind_raw = (getattr(b, "kind", "") or "").upper()
        tenant = (getattr(b, "tenant_name", "") or "").strip()
        if kind_raw == "GZ":
            tenant = (getattr(b, "gz_group_name", "") or "").strip()
        title = (getattr(b, "title", "") or "").strip()

        venue_id = int(getattr(b, "venue_id", 0) or 0)
        unit_id = getattr(b, "venue_unit_id", None)
        place = self._resolve_resource_name(venue_id, unit_id)

        self.lbl_d_main.setText(
            f"{b.starts_at:%d.%m.%Y} {b.starts_at:%H:%M}–{b.ends_at:%H:%M}\n"
            f"Арендатор: {tenant}\n"
            f"Событие: {title or '—'}"
        )
        self.lbl_d_extra.setText(
            f"Площадка: {place}\n"
            f"Тип: {self._kind_title(getattr(b, 'kind', ''))} | Статус: {self._status_title(getattr(b, 'status', ''))}"
        )

    # -------- column settings (grid) --------

    def _resource_key(self, r: Resource) -> str:
        if r.venue_unit_id is not None:
            return f"U:{int(r.venue_unit_id)}"
        return f"V:{int(r.venue_id)}"

    def _settings_key_for_org(self, org_id: int) -> str:
        return f"schedule/columns/org_{org_id}"

    def _load_columns_state(self, org_id: int) -> Dict[str, Dict]:
        k = self._settings_key_for_org(org_id)
        v = self._settings.value(k, None)
        return v if isinstance(v, dict) else {}

    def _save_columns_state(self, org_id: int, state: Dict[str, Dict]) -> None:
        self._settings.setValue(self._settings_key_for_org(org_id), state)

    def _apply_order_and_hidden(self, org_id: int) -> None:
        state = self._load_columns_state(org_id)

        changed = False
        for i, r in enumerate(self._resources):
            key = self._resource_key(r)
            if key not in state:
                state[key] = {"pos": i, "hidden": False}
                changed = True

        existing = {self._resource_key(r) for r in self._resources}
        for key in list(state.keys()):
            if key not in existing:
                state.pop(key, None)
                changed = True

        if changed:
            self._save_columns_state(org_id, state)

        self._resources.sort(key=lambda r: int(state[self._resource_key(r)].get("pos", 10_000)))

    def _apply_hidden_columns(self, org_id: int) -> None:
        state = self._load_columns_state(org_id)
        for i, r in enumerate(self._resources):
            key = self._resource_key(r)
            hidden = bool(state.get(key, {}).get("hidden", False))
            self.tbl.setColumnHidden(i + 1, hidden)

    # -------- actions (unchanged logic) --------

    def _on_columns(self):
        org_id = self.cmb_org.currentData()
        if org_id is None:
            return

        org_id = int(org_id)
        state = self._load_columns_state(org_id)

        dlg = QDialog(self)
        dlg.setWindowTitle("Колонки расписания")
        dlg.resize(560, 430)

        lst = QListWidget(dlg)
        lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        for r in self._resources:
            key = self._resource_key(r)
            it = QListWidgetItem(r.resource_name)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            hidden = bool(state.get(key, {}).get("hidden", False))
            it.setCheckState(Qt.CheckState.Unchecked if hidden else Qt.CheckState.Checked)
            lst.addItem(it)

        btn_up = QPushButton("Вверх")
        btn_down = QPushButton("Вниз")
        btn_all = QPushButton("Показать все")
        btn_none = QPushButton("Скрыть все")
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Отмена")

        def move(delta: int):
            row = lst.currentRow()
            if row < 0:
                return
            row2 = row + delta
            if row2 < 0 or row2 >= lst.count():
                return
            it = lst.takeItem(row)
            lst.insertItem(row2, it)
            lst.setCurrentRow(row2)

        btn_up.clicked.connect(lambda: move(-1))
        btn_down.clicked.connect(lambda: move(+1))

        def set_all(checked: bool):
            for i in range(lst.count()):
                it = lst.item(i)
                it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

        btn_all.clicked.connect(lambda: set_all(True))
        btn_none.clicked.connect(lambda: set_all(False))

        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)

        right = QVBoxLayout()
        right.addWidget(btn_up)
        right.addWidget(btn_down)
        right.addSpacing(12)
        right.addWidget(btn_all)
        right.addWidget(btn_none)
        right.addStretch(1)
        right.addWidget(btn_ok)
        right.addWidget(btn_cancel)

        lay = QHBoxLayout(dlg)
        lay.addWidget(lst, 1)
        lay.addLayout(right)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_state: Dict[str, Dict] = dict(state)
        for pos in range(lst.count()):
            it = lst.item(pos)
            key = str(it.data(Qt.ItemDataRole.UserRole))
            shown = (it.checkState() == Qt.CheckState.Checked)
            new_state.setdefault(key, {})
            new_state[key]["pos"] = pos
            new_state[key]["hidden"] = (not shown)

        self._save_columns_state(org_id, new_state)
        self._apply_order_and_hidden(org_id)
        self._setup_table()
        self._apply_hidden_columns(org_id)
        self.reload()

    def _on_create(self):
        org_id = self.cmb_org.currentData()
        if org_id is None:
            return
    
        acc = get_org_access(int(self.user.id), str(self.user.role_code), int(org_id))
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование расписания этого учреждения.")
            return
    
        if self._mode() != "grid":
            QMessageBox.information(self, "Создать бронь", "Создание доступно в режиме 'Слоты'.")
            return
    
        it = self.tbl.currentItem()
        if not it:
            QMessageBox.information(self, "Создать бронь", "Выберите слот.")
            return
    
        if it.column() <= 0:
            QMessageBox.information(self, "Создать бронь", "Выберите слот на площадке/зоне (не колонку 'Время').")
            return
    
        # если в ячейке уже есть бронь — открываем редактирование
        b0 = it.data(Qt.ItemDataRole.UserRole)
        if b0:
            self._on_edit()
            return
    
        day = self.dt_day.date().toPython()
    
        sel = self._selected_multi_units()
        if sel:
            cols, rmin, rmax = sel
            r0, r1 = rmin, rmax
        else:
            cols = [it.column()]
            r0 = it.row()
            r1 = it.row()
    
        # не даём смешивать разные площадки
        venue_ids = {int(self._resources[c - 1].venue_id) for c in cols}
        if len(venue_ids) != 1:
            QMessageBox.information(self, "Создать бронь", "Выберите зоны в рамках одной площадки.")
            return
    
        starts_at = self._row_to_datetime(day, r0)
        ends_at = self._row_to_datetime(day, r1) + timedelta(minutes=self.SLOT_MINUTES)
    
        # проверка: в выделении не должно быть существующих броней
        for c in cols:
            it_cell = self.tbl.item(r0, c)
            if it_cell and it_cell.data(Qt.ItemDataRole.UserRole):
                QMessageBox.information(self, "Создать бронь", "В выделении есть занятые слоты. Уберите их из выделения.")
                return
    
        # берём данные площадки из первой выбранной колонки
        col0 = cols[0]
        rsrc0 = self._resources[col0 - 1]
        venue_id = int(rsrc0.venue_id)
        venue_name = str(rsrc0.venue_name)
    
        # если выделено несколько зон — фиксируем зоны и только показываем список
        multi_cols = (len(cols) > 1)
    
        # список выбранных зон для отображения в диалоге
        selected_lines = [self._resources[c - 1].resource_name for c in cols]
    
        # список зон для выбранной площадки (показывать комбобокс "Зона" имеет смысл только при одиночном создании)
        venue_units = None
        if not multi_cols:
            try:
                units = list_venue_units(venue_id, include_inactive=False)
                if units:
                    venue_units = [{"id": u.id, "name": u.name} for u in units]
            except Exception:
                venue_units = None
    
        # initial unit: если одиночное выделение — ставим unit из колонки
        unit0 = rsrc0.venue_unit_id
        venue_unit_id = int(unit0) if unit0 is not None else None
    
        allowed_kinds = self._allowed_booking_kinds()
        default_kind = "GZ" if ("GZ" in allowed_kinds and "PD" not in allowed_kinds) else "PD"
        
        dlg = BookingDialog(
            self,
            title="Создать бронь",
            starts_at=starts_at,
            ends_at=ends_at,
            tenants=self._tenants,
            gz_groups=self._gz_groups,
            venue_name=venue_name,
            venue_units=venue_units,
            initial={"venue_unit_id": venue_unit_id, "kind": default_kind, "title": ""},
            selection_title=(f"Выбрано зон: {len(selected_lines)}" if multi_cols else None),
            selection_lines=(selected_lines if multi_cols else None),
            allowed_kinds=allowed_kinds,
        )

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
    
        data = dlg.values()
    
        kind = str(data.get("kind") or "PD").upper()
        tenant_id = int(data["tenant_id"]) if data.get("tenant_id") is not None else None
        gz_group_id = int(data["gz_group_id"]) if data.get("gz_group_id") is not None else None
        title = str(data.get("title") or "")
        
        created = 0
        skipped = 0
        errors = []
    
        if multi_cols:
            # создаём по одной брони на каждую выбранную зону/колонку
            for c in cols:
                rsrc = self._resources[c - 1]
                unit_id = int(rsrc.venue_unit_id) if rsrc.venue_unit_id is not None else None
                try:
                    create_booking(
                        venue_id=int(rsrc.venue_id),
                        venue_unit_id=unit_id,
                        tenant_id=tenant_id,
                        gz_group_id=gz_group_id,
                        title=title,
                        kind=kind,
                        starts_at=starts_at,
                        ends_at=ends_at,
                    )
                    created += 1
                except Exception as e:
                    skipped += 1
                    errors.append(str(e))
    
            if skipped:
                msg = f"Создано: {created}\nПропущено: {skipped}"
                if errors:
                    msg += "\n\nПервые ошибки:\n" + "\n".join(errors[:6])
                QMessageBox.information(self, "Создание бронирований", msg)
        else:
            # одиночное создание: берём venue_unit_id из диалога (если он показан)
            try:
                create_booking(
                    venue_id=venue_id,
                    venue_unit_id=(int(data["venue_unit_id"]) if data.get("venue_unit_id") is not None else None),
                    tenant_id=tenant_id,
                    gz_group_id=gz_group_id,
                    title=title,
                    kind=kind,
                    starts_at=starts_at,
                    ends_at=ends_at,
                )
            except Exception as e:
                _uilog("ERROR create_booking: " + repr(e))
                _uilog(traceback.format_exc())
                QMessageBox.critical(self, "Создать бронь", f"Ошибка создания:\n{e}")
                return
    
        self.reload()

    def _on_edit(self):
        org_id = self.cmb_org.currentData()
        if org_id is None:
            return
    
        acc = get_org_access(int(self.user.id), str(self.user.role_code), int(org_id))
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование расписания этого учреждения.")
            return
    
        b = self._selected_booking()
        if not b:
            QMessageBox.information(self, "Редактировать", "Выберите бронирование.")
            return

        venue_id = int(getattr(b, "venue_id"))
        venue_unit_id = getattr(b, "venue_unit_id", None)
        venue_unit_id = int(venue_unit_id) if venue_unit_id is not None else None
    
        starts_at = getattr(b, "starts_at")
        ends_at = getattr(b, "ends_at")
    
        # найдём читаемое имя площадки
        venue_name = ""
        for r in self._resources:
            if int(r.venue_id) == venue_id:
                venue_name = str(r.venue_name)
                break
        if not venue_name:
            venue_name = f"Площадка {venue_id}"
    
        venue_units = None
        try:
            units = list_venue_units(venue_id, include_inactive=False)
            if units:
                venue_units = [{"id": u.id, "name": u.name} for u in units]
        except Exception:
            venue_units = None
    
        initial = {
            "kind": getattr(b, "kind", "PD"),
            "tenant_id": getattr(b, "tenant_id", None),
            "gz_group_id": getattr(b, "gz_group_id", None),
            "venue_unit_id": venue_unit_id,
            "title": getattr(b, "title", ""),
        }
    
        allowed_kinds = self._allowed_booking_kinds()
        
        dlg = BookingDialog(
            self,
            title="Редактировать бронь",
            starts_at=starts_at,
            ends_at=ends_at,
            tenants=self._tenants,
            gz_groups=self._gz_groups,
            venue_name=venue_name,
            venue_units=venue_units,
            initial=initial,
            allowed_kinds=allowed_kinds,
        )

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
    
        data = dlg.values()
        
        kind = str(data.get("kind") or "PD").upper()
        tenant_id = int(data["tenant_id"]) if data.get("tenant_id") is not None else None
        gz_group_id = int(data["gz_group_id"]) if data.get("gz_group_id") is not None else None
        
        try:
            update_booking(
                int(getattr(b, "id")),
                tenant_id=tenant_id,
                gz_group_id=gz_group_id,
                title=str(data.get("title") or ""),
                kind=kind,
                venue_unit_id=(int(data["venue_unit_id"]) if data.get("venue_unit_id") is not None else None),
            )
        except Exception as e:

            _uilog("ERROR update_booking: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(self, "Редактировать", f"Ошибка сохранения:\n{e}")
            return
    
        self.reload()

    def _on_cancel(self):
        org_id = self.cmb_org.currentData()
        if org_id is None:
            return
        
        acc = get_org_access(int(self.user.id), str(self.user.role_code), int(org_id))
        if not acc.can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование расписания этого учреждения.")
            return
        b = self._selected_booking()
        if not b:
            QMessageBox.information(self, "Отменить", "Выберите бронирование.")
            return
    
        if (
            QMessageBox.question(
                self,
                "Отмена бронирования",
                "Отменить выбранное бронирование?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
    
        try:
            cancel_booking(int(getattr(b, "id")))
        except Exception as e:
            _uilog("ERROR cancel: " + repr(e))
            _uilog(traceback.format_exc())
            QMessageBox.critical(self, "Отменить", f"Ошибка отмены:\n{e}")
            return
    
        self.reload()

    def _allowed_booking_kinds(self) -> set[str]:
        if (self.user.role_code or "").lower() == "admin":
            return {"PD", "GZ"}
    
        perms = self.user.permissions or set()
    
        allowed: set[str] = set()
        if "tab.tenants" in perms:
            allowed.add("PD")
        if "tab.gz" in perms:
            allowed.add("GZ")
    
        return allowed or {"PD"}

    def _lighten(self, color: QColor, steps: int = 2, amount: int = 120) -> QColor:
        """
        steps=2 -> два тона светлее.
        amount: 0..200, 100 примерно без изменений, больше -> светлее.
        """
        c = QColor(color)
        for _ in range(max(0, int(steps))):
            c = c.lighter(int(amount))
        return c
