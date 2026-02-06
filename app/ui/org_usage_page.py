from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, timezone
from typing import List, Dict, Tuple, Optional, Set

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush
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
    QHeaderView,
    QProgressBar,
    QSplitter,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)

from app.services.ref_service import list_active_orgs
from app.services.usage_service import calc_usage_by_venues, UsageRow
from app.ui.usage_details_widget import UsageDetailsWidget, UsageTotals


ROLE_IS_TOTAL = Qt.ItemDataRole.UserRole + 50


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    title: str


def _pct(sec: int, cap: int) -> float:
    return 0.0 if cap <= 0 else 100.0 * (sec / cap)


def _hours(sec: int) -> float:
    return round(sec / 3600.0, 1)

class UsageRowDelegate(QStyledItemDelegate):
    """
    Делегат для usageTable.
    Итоговые строки (ROLE_IS_TOTAL=True) — рисуем ВСЁ сами,
    чтобы QSS не перебил фон.
    Обычные строки — стандартный paint.
    """

    TOTAL_BG     = QColor(40, 42, 80)       # непрозрачный тёмно-индиго
    TOTAL_BG_SEL = QColor(55, 58, 110)      # чуть светлее при selection
    TOTAL_BORDER = QColor(99, 102, 241, 60) # линия-разделитель снизу
    TOTAL_FG     = QColor(255, 255, 255, 235)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        is_total = index.data(ROLE_IS_TOTAL)

        if not is_total:
            super().paint(painter, option, index)
            return

        # ── Итоговая строка: рисуем всё сами ──
        painter.save()
        r = option.rect

        # 1. Фон — непрозрачный, QSS не перебьёт
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(r, self.TOTAL_BG_SEL)
        else:
            painter.fillRect(r, self.TOTAL_BG)

        # 2. Линия-разделитель снизу
        painter.setPen(QPen(self.TOTAL_BORDER, 1))
        painter.drawLine(r.bottomLeft(), r.bottomRight())

        # 3. Текст
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if text:
            font = index.data(Qt.ItemDataRole.FontRole)
            if isinstance(font, QFont):
                painter.setFont(font)
            else:
                painter.setFont(option.font)

            painter.setPen(self.TOTAL_FG)

            # Определяем alignment
            align = index.data(Qt.ItemDataRole.TextAlignmentRole)
            if align is None:
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

            # Отступы как в QSS: padding 6px 10px
            text_rect = r.adjusted(10, 0, -10, 0)
            painter.drawText(text_rect, int(align), text)

        painter.restore()

class OrgUsagePage(QWidget):
    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

        self._period: Optional[Period] = None
        self._rows: List[UsageRow] = []

        self.lbl_title = QLabel("Загрузка учреждений")
        self.lbl_title.setObjectName("sectionTitle")

        self.cmb_org = QComboBox()
        self.cmb_org.addItem("Все учреждения", None)

        self.cmb_period = QComboBox()
        self.cmb_period.addItem("День", "day")
        self.cmb_period.addItem("Неделя (Пн–Вс)", "week")
        self.cmb_period.addItem("Месяц", "month")
        self.cmb_period.addItem("Квартал", "quarter")
        self.cmb_period.addItem("Год", "year")

        self.dt_anchor = QDateEdit()
        self.dt_anchor.setCalendarPopup(True)
        self.dt_anchor.setDate(date.today())
        self.dt_anchor.setDisplayFormat("dd.MM.yyyy")
        self.dt_anchor.setFixedWidth(130)

        self.cb_cancelled = QCheckBox("Отменённые")
        self.cb_cancelled.setChecked(False)

        self.btn_refresh = QPushButton("Обновить")

        self.cmb_org.currentIndexChanged.connect(lambda *_: self.reload())
        self.cmb_period.currentIndexChanged.connect(lambda *_: self.reload())
        self.dt_anchor.dateChanged.connect(lambda *_: self.reload())
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())
        self.btn_refresh.clicked.connect(self.reload)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        top.addWidget(self.lbl_title)
        top.addWidget(QLabel("Учреждение:"))
        top.addWidget(self.cmb_org, 1)
        top.addWidget(QLabel("Период:"))
        top.addWidget(self.cmb_period)
        top.addWidget(QLabel("Дата:"))
        top.addWidget(self.dt_anchor)
        top.addWidget(self.cb_cancelled)
        top.addWidget(self.btn_refresh)

        self.lbl_period = QLabel("")
        self.lbl_period.setObjectName("scheduleMeta")

        self.lbl_total = QLabel("")
        self.lbl_total.setObjectName("scheduleMetaStrong")

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.addWidget(self.lbl_period, 1)
        meta.addWidget(self.lbl_total, 0, Qt.AlignmentFlag.AlignRight)

        self.tbl = QTableWidget(0, 7)
        self.tbl.setObjectName("usageTable")
        self.tbl.setHorizontalHeaderLabels(
            ["Учреждение", "Площадка", "Загрузка", "Итого, %", "ПД, ч", "ГЗ, ч", "Итого, ч"]
        )
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(False)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.itemSelectionChanged.connect(self._on_selection_changed)

        # делегат для подсветки итоговых строк
        self._row_delegate = UsageRowDelegate(self.tbl)
        self.tbl.setItemDelegate(self._row_delegate)

        header = self.tbl.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for c in (3, 4, 5, 6):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        self.details = UsageDetailsWidget(self)
        self.details.set_shift_titles("Утро", "День", "Вечер")

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.tbl)
        splitter.addWidget(self.details)
        self.details.setMinimumWidth(420)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([800, 420])

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addLayout(meta)
        root.addWidget(splitter, 1)

        QTimer.singleShot(0, self._load_orgs)

    def _load_orgs(self):
        try:
            orgs = list_active_orgs()
            self.cmb_org.blockSignals(True)
            while self.cmb_org.count() > 1:
                self.cmb_org.removeItem(1)
            for o in orgs:
                self.cmb_org.addItem(o.name, o.id)
            self.cmb_org.blockSignals(False)
        except Exception as e:
            QMessageBox.critical(self, "Загрузка учреждений", f"Ошибка загрузки учреждений:\n{e}")
            return
        self.reload()

    def _calc_period(self) -> Period:
        mode = self.cmb_period.currentData()
        d = self.dt_anchor.date().toPython()

        if mode == "day":
            return Period(start=d, end=d, title=f"{d:%d.%m.%Y}")
        if mode == "week":
            start = d - timedelta(days=d.weekday())
            end = start + timedelta(days=6)
            return Period(start=start, end=end, title=f"Неделя: {start:%d.%m.%Y} – {end:%d.%m.%Y}")
        if mode == "month":
            start = d.replace(day=1)
            nm = start.replace(year=start.year + 1, month=1, day=1) if start.month == 12 else start.replace(month=start.month + 1, day=1)
            end = nm - timedelta(days=1)
            return Period(start=start, end=end, title=f"Месяц: {start:%m.%Y} ({start:%d.%m.%Y} – {end:%d.%m.%Y})")
        if mode == "quarter":
            q = (d.month - 1) // 3 + 1
            sm = 3 * (q - 1) + 1
            start = d.replace(month=sm, day=1)
            nq = start.replace(year=start.year + 1, month=1, day=1) if sm == 10 else start.replace(month=sm + 3, day=1)
            end = nq - timedelta(days=1)
            return Period(start=start, end=end, title=f"Квартал Q{q}: {start:%d.%m.%Y} – {end:%d.%m.%Y}")
        if mode == "year":
            start = d.replace(month=1, day=1)
            end = d.replace(month=12, day=31)
            return Period(start=start, end=end, title=f"Год: {d.year}")
        return Period(start=d, end=d, title=f"{d:%d.%m.%Y}")

    def _make_progress(self, pct: float, *, is_total: bool = False) -> QProgressBar:
        pb = QProgressBar()
        pb.setRange(0, 100)
        pb.setValue(max(0, min(100, int(round(pct)))))
        pb.setTextVisible(True)
        pb.setFormat(f"{pct:.1f}%")
    
        if pct >= 100:
            chunk = "#22c55e"
        elif pct >= 71:
            chunk = "#facc15"
        elif pct >= 51:
            chunk = "#f59e0b"
        elif pct >= 1:
            chunk = "#ef4444"
        else:
            chunk = "rgba(255,255,255,0.18)"
    
        if is_total:
            bg = "transparent"
            br = "rgba(255,255,255,0.10)"
        else:
            bg = "rgba(11,18,32,0.65)"
            br = "rgba(255,255,255,0.14)"
    
        pb.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {br};
                border-radius: 8px;
                background: {bg};
                text-align: center;
                padding: 2px;
                min-width: 120px;
                color: rgba(255,255,255,0.90);
            }}
            QProgressBar::chunk {{
                background: {chunk};
                border-radius: 8px;
            }}
        """)
    
        return pb

    def _apply_shift_titles(self, *, m_cap: int, d_cap: int, e_cap: int) -> None:
        m = "Утро (в пределах режима)" if m_cap > 0 else "Утро (нет)"
        d = "День (в пределах режима)" if d_cap > 0 else "День (нет)"
        e = "Вечер (в пределах режима)" if e_cap > 0 else "Вечер (нет)"
        self.details.set_shift_titles(m, d, e)

    def reload(self):
        p = self._calc_period()
        self._period = p
        self.lbl_period.setText(f"Период: {p.title}")

        org_id = self.cmb_org.currentData()
        include_cancelled = self.cb_cancelled.isChecked()

        try:
            rows = calc_usage_by_venues(
                start_day=p.start,
                end_day=p.end,
                tz=self.TZ,
                org_id=(int(org_id) if org_id is not None else None),
                include_cancelled=include_cancelled,
            )
        except Exception as e:
            QMessageBox.critical(self, "Загрузка учреждений", f"Ошибка расчёта:\n{e}")
            return

        self._rows = list(rows)

        cap = sum(r.capacity_sec for r in rows)
        pd = sum(r.pd_sec for r in rows)
        gz = sum(r.gz_sec for r in rows)
        busy = pd + gz
        self.lbl_total.setText(
            f"ИТОГО: ПД {_hours(pd)}ч ({_pct(pd, cap):.1f}%) | "
            f"ГЗ {_hours(gz)}ч ({_pct(gz, cap):.1f}%) | "
            f"Занято {_hours(busy)}ч ({_pct(busy, cap):.1f}%)"
        )

        by_org: Dict[Tuple[int, str], List[UsageRow]] = {}
        for r in rows:
            by_org.setdefault((r.org_id, r.org_name), []).append(r)

        def org_total_ratio(k):
            rr = by_org[k]
            c0 = sum(x.capacity_sec for x in rr)
            b0 = sum(x.pd_sec + x.gz_sec for x in rr)
            return (b0 / c0) if c0 else 0.0

        org_keys = sorted(by_org.keys(), key=org_total_ratio, reverse=True)

        self.tbl.setRowCount(0)

        for (oid, oname) in org_keys:
            org_rows = by_org[(oid, oname)]

            org_cap = sum(x.capacity_sec for x in org_rows)
            org_pd = sum(x.pd_sec for x in org_rows)
            org_gz = sum(x.gz_sec for x in org_rows)
            org_busy = org_pd + org_gz
            org_pct = _pct(org_busy, org_cap)

            r0 = self.tbl.rowCount()
            self.tbl.insertRow(r0)

            it_org = QTableWidgetItem(oname)
            it_venue = QTableWidgetItem("ИТОГО по учреждению")
            bf = self._bold_font()
            it_org.setFont(bf)
            it_venue.setFont(bf)
            it_org.setData(Qt.ItemDataRole.UserRole, ("org", oid))
            it_venue.setData(Qt.ItemDataRole.UserRole, ("org", oid))

            # пометка "итого" для делегата
            it_org.setData(ROLE_IS_TOTAL, True)
            it_venue.setData(ROLE_IS_TOTAL, True)

            self.tbl.setItem(r0, 0, it_org)
            self.tbl.setItem(r0, 1, it_venue)
            self.tbl.setCellWidget(r0, 2, self._make_progress(org_pct, is_total=True))

            for ci, txt in ((3, f"{org_pct:.1f}%"),
                            (4, f"{_hours(org_pd):.1f}"),
                            (5, f"{_hours(org_gz):.1f}"),
                            (6, f"{_hours(org_busy):.1f}")):
                it = QTableWidgetItem(txt)
                it.setFont(bf)
                it.setData(ROLE_IS_TOTAL, True)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl.setItem(r0, ci, it)

            # venue rows
            org_rows.sort(key=lambda x: (x.total_sec / x.capacity_sec) if x.capacity_sec else 0.0, reverse=True)
            for v in org_rows:
                rr = self.tbl.rowCount()
                self.tbl.insertRow(rr)

                busy_v = v.pd_sec + v.gz_sec
                pct_v = _pct(busy_v, v.capacity_sec)

                it0 = QTableWidgetItem(oname)
                it1 = QTableWidgetItem(v.venue_name)
                it0.setData(Qt.ItemDataRole.UserRole, ("venue", v.venue_id))
                it1.setData(Qt.ItemDataRole.UserRole, ("venue", v.venue_id))

                self.tbl.setItem(rr, 0, it0)
                self.tbl.setItem(rr, 1, it1)
                self.tbl.setCellWidget(rr, 2, self._make_progress(pct_v))
                self.tbl.setItem(rr, 3, QTableWidgetItem(f"{pct_v:.1f}%"))
                self.tbl.setItem(rr, 4, QTableWidgetItem(f"{_hours(v.pd_sec):.1f}"))
                self.tbl.setItem(rr, 5, QTableWidgetItem(f"{_hours(v.gz_sec):.1f}"))
                self.tbl.setItem(rr, 6, QTableWidgetItem(f"{_hours(busy_v):.1f}"))

                for c in (3, 4, 5, 6):
                    it = self.tbl.item(rr, c)
                    if it:
                        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if self.tbl.rowCount() > 0:
            self.tbl.setCurrentCell(0, 0)
            self._on_selection_changed()
        else:
            self.details.set_data(None)

    def _on_selection_changed(self):
        if not self._period:
            self.details.set_data(None)
            return

        row = self.tbl.currentRow()
        if row < 0:
            self.details.set_data(None)
            return

        it = self.tbl.item(row, 0) or self.tbl.item(row, 1)
        if not it:
            self.details.set_data(None)
            return

        tag = it.data(Qt.ItemDataRole.UserRole)
        if not tag or not isinstance(tag, tuple) or len(tag) != 2:
            self.details.set_data(None)
            return

        kind, obj_id = tag

        if kind == "venue":
            v = next((x for x in self._rows if int(x.venue_id) == int(obj_id)), None)
            if not v:
                self.details.set_data(None)
                return
            self._apply_shift_titles(m_cap=v.morning_capacity_sec, d_cap=v.day_capacity_sec, e_cap=v.evening_capacity_sec)
            self.details.set_data(UsageTotals(
                title=f"Площадка: {v.venue_name}", period_title=self._period.title,
                cap_sec=v.capacity_sec, pd_sec=v.pd_sec, gz_sec=v.gz_sec,
                m_cap=v.morning_capacity_sec, m_pd=v.morning_pd_sec, m_gz=v.morning_gz_sec,
                d_cap=v.day_capacity_sec, d_pd=v.day_pd_sec, d_gz=v.day_gz_sec,
                e_cap=v.evening_capacity_sec, e_pd=v.evening_pd_sec, e_gz=v.evening_gz_sec,
            ))
            return

        if kind == "org":
            org_rows = [x for x in self._rows if int(x.org_id) == int(obj_id)]
            if not org_rows:
                self.details.set_data(None)
                return
            m_cap = sum(x.morning_capacity_sec for x in org_rows)
            d_cap = sum(x.day_capacity_sec for x in org_rows)
            e_cap = sum(x.evening_capacity_sec for x in org_rows)
            self._apply_shift_titles(m_cap=m_cap, d_cap=d_cap, e_cap=e_cap)
            cap = sum(x.capacity_sec for x in org_rows)
            pd = sum(x.pd_sec for x in org_rows)
            gz = sum(x.gz_sec for x in org_rows)
            self.details.set_data(UsageTotals(
                title=f"Учреждение: {org_rows[0].org_name}", period_title=self._period.title,
                cap_sec=cap, pd_sec=pd, gz_sec=gz,
                m_cap=m_cap, m_pd=sum(x.morning_pd_sec for x in org_rows), m_gz=sum(x.morning_gz_sec for x in org_rows),
                d_cap=d_cap, d_pd=sum(x.day_pd_sec for x in org_rows), d_gz=sum(x.day_gz_sec for x in org_rows),
                e_cap=e_cap, e_pd=sum(x.evening_pd_sec for x in org_rows), e_gz=sum(x.evening_gz_sec for x in org_rows),
            ))
            return

        self.details.set_data(None)

    def _bold_font(self) -> QFont:
        f = QFont(self.tbl.font())
        f.setBold(True)
        return f
