from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta, timezone
from typing import List, Dict, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
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
)

from app.services.ref_service import list_active_orgs
from app.services.usage_service import calc_usage_by_venues, UsageRow


_PAGE_QSS = """
QWidget { background: #fbfbfc; }
QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 6px 10px;
    min-height: 22px;
}
QComboBox:focus, QDateEdit:focus { border: 1px solid #7fb3ff; }
QPushButton {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 600;
    min-height: 34px;
}
QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
QPushButton:pressed { background: #eef1f5; }
QCheckBox { padding: 0 6px; }
QLabel#sectionTitle { color: #111111; font-weight: 700; padding: 0 4px; }
QTableWidget {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    selection-background-color: rgba(127,179,255,60);
    selection-color: #111111;
    gridline-color: #e9edf3;
}
QHeaderView::section {
    background: #f6f7f9;
    color: #111111;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #e6e6e6;
    font-weight: 600;
}
QTableWidget::item { padding: 6px 10px; }
"""


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    title: str


class OrgUsagePage(QWidget):
    WORK_START = time(8, 0)
    WORK_END = time(22, 0)

    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_PAGE_QSS)

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
        top.setContentsMargins(12, 12, 12, 8)
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
        self.lbl_period.setStyleSheet("color:#334155; padding:0 4px;")

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("color:#0f172a; font-weight:600; padding:0 4px;")

        meta = QHBoxLayout()
        meta.setContentsMargins(12, 0, 12, 0)
        meta.addWidget(self.lbl_period, 1)
        meta.addWidget(self.lbl_total, 0, Qt.AlignmentFlag.AlignRight)

        # Таблица:
        # 0 Учреждение
        # 1 Площадка
        # 2 Полоса (общая загрузка)
        # 3 Доступно, ч
        # 4 ПД, ч
        # 5 ПД, %
        # 6 ГЗ, ч
        # 7 ГЗ, %
        # 8 Итого, %
        # 9..13  Утро:  ПД ч, ПД %, ГЗ ч, ГЗ %, Итого %
        # 14..18 День:  ПД ч, ПД %, ГЗ ч, ГЗ %, Итого %
        # 19..23 Вечер: ПД ч, ПД %, ГЗ ч, ГЗ %, Итого %
        self.tbl = QTableWidget(0, 24)
        self.tbl.setHorizontalHeaderLabels(
            [
                "Учреждение",
                "Площадка",
                "Полоса",
                "Доступно, ч",
                "ПД, ч",
                "ПД, %",
                "ГЗ, ч",
                "ГЗ, %",
                "Итого, %",
                "Утро ПД, ч",
                "Утро ПД, %",
                "Утро ГЗ, ч",
                "Утро ГЗ, %",
                "Утро Итог, %",
                "День ПД, ч",
                "День ПД, %",
                "День ГЗ, ч",
                "День ГЗ, %",
                "День Итог, %",
                "Вечер ПД, ч",
                "Вечер ПД, %",
                "Вечер ГЗ, ч",
                "Вечер ГЗ, %",
                "Вечер Итог, %",
            ]
        )

        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setShowGrid(True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSortingEnabled(False)

        header = self.tbl.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(3, self.tbl.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addLayout(meta)
        root.addWidget(self.tbl, 1)

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
        start = d - timedelta(days=d.weekday())  # Пн
        end = start + timedelta(days=6)          # Вс
        return Period(start=start, end=end, title=f"Неделя: {start:%d.%m.%Y} – {end:%d.%m.%Y}")

    if mode == "month":
        start = d.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1, day=1)
        else:
            next_month = start.replace(month=start.month + 1, day=1)
        end = next_month - timedelta(days=1)
        return Period(
            start=start,
            end=end,
            title=f"Месяц: {start:%m.%Y} ({start:%d.%m.%Y} – {end:%d.%m.%Y})",
        )

    if mode == "quarter":
        q = (d.month - 1) // 3 + 1
        start_month = 3 * (q - 1) + 1
        start = d.replace(month=start_month, day=1)
        if start_month == 10:
            next_q = start.replace(year=start.year + 1, month=1, day=1)
        else:
            next_q = start.replace(month=start_month + 3, day=1)
        end = next_q - timedelta(days=1)
        return Period(start=start, end=end, title=f"Квартал Q{q}: {start:%d.%m.%Y} – {end:%d.%m.%Y}")

    if mode == "year":
        start = d.replace(month=1, day=1)
        end = d.replace(month=12, day=31)
        return Period(start=start, end=end, title=f"Год: {d.year}")

    return Period(start=d, end=d, title=f"{d:%d.%m.%Y}")

    def reload(self):
        p = self._calc_period()
        self.lbl_period.setText(f"Период: {p.title}")

        org_id = self.cmb_org.currentData()
        include_cancelled = self.cb_cancelled.isChecked()

        try:
            rows: List[UsageRow] = calc_usage_by_venues(
                start_day=p.start,
                end_day=p.end,
                tz=self.TZ,
                org_id=(int(org_id) if org_id is not None else None),
                include_cancelled=include_cancelled,
                work_start=self.WORK_START,
                work_end=self.WORK_END,
            )
        except Exception as e:
            QMessageBox.critical(self, "Загрузка учреждений", f"Ошибка расчёта:\n{e}")
            return

        cap = sum(r.capacity_sec for r in rows)
        pd = sum(r.pd_sec for r in rows)
        gz = sum(r.gz_sec for r in rows)
        tot = pd + gz
        self.lbl_total.setText(
            f"ИТОГО: ПД {self._hours(pd)}ч ({self._pct(pd, cap)}%) | "
            f"ГЗ {self._hours(gz)}ч ({self._pct(gz, cap)}%) | "
            f"Занято {self._hours(tot)}ч ({self._pct(tot, cap)}%)"
        )

        # группировка по учреждению
        by_org: Dict[Tuple[int, str], List[UsageRow]] = {}
        for r in rows:
            by_org.setdefault((r.org_id, r.org_name), []).append(r)

        def org_sort_key(k):
            org_rows = by_org[k]
            cap0 = sum(x.capacity_sec for x in org_rows)
            tot0 = sum(x.total_sec for x in org_rows)
            return (tot0 / cap0) if cap0 else 0.0

        org_keys = sorted(by_org.keys(), key=org_sort_key, reverse=True)

        self.tbl.setRowCount(0)
        self.tbl.setSortingEnabled(False)

        for (oid, oname) in org_keys:
            org_rows = by_org[(oid, oname)]

            # итог по учреждению
            org_cap = sum(x.capacity_sec for x in org_rows)
            org_pd = sum(x.pd_sec for x in org_rows)
            org_gz = sum(x.gz_sec for x in org_rows)
            org_tot = org_pd + org_gz

            org_m_cap = sum(x.morning_capacity_sec for x in org_rows)
            org_d_cap = sum(x.day_capacity_sec for x in org_rows)
            org_e_cap = sum(x.evening_capacity_sec for x in org_rows)

            org_m_pd = sum(x.morning_pd_sec for x in org_rows)
            org_m_gz = sum(x.morning_gz_sec for x in org_rows)
            org_d_pd = sum(x.day_pd_sec for x in org_rows)
            org_d_gz = sum(x.day_gz_sec for x in org_rows)
            org_e_pd = sum(x.evening_pd_sec for x in org_rows)
            org_e_gz = sum(x.evening_gz_sec for x in org_rows)

            self._add_row(
                org_name=oname,
                venue_name="ИТОГО по учреждению",
                is_total=True,
                cap_sec=org_cap,
                pd_sec=org_pd,
                gz_sec=org_gz,
                m_cap=org_m_cap,
                m_pd=org_m_pd,
                m_gz=org_m_gz,
                d_cap=org_d_cap,
                d_pd=org_d_pd,
                d_gz=org_d_gz,
                e_cap=org_e_cap,
                e_pd=org_e_pd,
                e_gz=org_e_gz,
            )

            # площадки внутри учреждения — сортировка по загрузке
            org_rows.sort(key=lambda x: (x.total_sec / x.capacity_sec) if x.capacity_sec else 0.0, reverse=True)
            for r in org_rows:
                self._add_row(
                    org_name=oname,
                    venue_name=r.venue_name,
                    is_total=False,
                    cap_sec=r.capacity_sec,
                    pd_sec=r.pd_sec,
                    gz_sec=r.gz_sec,
                    m_cap=r.morning_capacity_sec,
                    m_pd=r.morning_pd_sec,
                    m_gz=r.morning_gz_sec,
                    d_cap=r.day_capacity_sec,
                    d_pd=r.day_pd_sec,
                    d_gz=r.day_gz_sec,
                    e_cap=r.evening_capacity_sec,
                    e_pd=r.evening_pd_sec,
                    e_gz=r.evening_gz_sec,
                )

        self.tbl.resizeRowsToContents()

    def _add_row(
        self,
        *,
        org_name: str,
        venue_name: str,
        is_total: bool,
        cap_sec: int,
        pd_sec: int,
        gz_sec: int,
        m_cap: int,
        m_pd: int,
        m_gz: int,
        d_cap: int,
        d_pd: int,
        d_gz: int,
        e_cap: int,
        e_pd: int,
        e_gz: int,
    ):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)

        it_org = QTableWidgetItem(org_name)
        it_venue = QTableWidgetItem(venue_name)

        if is_total:
            it_org.setFont(self._bold_font())
            it_venue.setFont(self._bold_font())

        self.tbl.setItem(row, 0, it_org)
        self.tbl.setItem(row, 1, it_venue)

        total_sec = int(pd_sec) + int(gz_sec)
        total_pct = self._pct(total_sec, cap_sec)
        self.tbl.setCellWidget(row, 2, self._make_progress(total_pct))

        self._set_num(self.tbl, row, 3, f"{self._hours(cap_sec):.2f}")
        self._set_num(self.tbl, row, 4, f"{self._hours(pd_sec):.2f}")
        self._set_num(self.tbl, row, 5, f"{self._pct(pd_sec, cap_sec):.1f}%")
        self._set_num(self.tbl, row, 6, f"{self._hours(gz_sec):.2f}")
        self._set_num(self.tbl, row, 7, f"{self._pct(gz_sec, cap_sec):.1f}%")
        self._set_num(self.tbl, row, 8, f"{total_pct:.1f}%")

        # Утро
        m_total = m_pd + m_gz
        self._set_num(self.tbl, row, 9, f"{self._hours(m_pd):.2f}")
        self._set_num(self.tbl, row, 10, f"{self._pct(m_pd, m_cap):.1f}%")
        self._set_num(self.tbl, row, 11, f"{self._hours(m_gz):.2f}")
        self._set_num(self.tbl, row, 12, f"{self._pct(m_gz, m_cap):.1f}%")
        self._set_num(self.tbl, row, 13, f"{self._pct(m_total, m_cap):.1f}%")

        # День
        d_total = d_pd + d_gz
        self._set_num(self.tbl, row, 14, f"{self._hours(d_pd):.2f}")
        self._set_num(self.tbl, row, 15, f"{self._pct(d_pd, d_cap):.1f}%")
        self._set_num(self.tbl, row, 16, f"{self._hours(d_gz):.2f}")
        self._set_num(self.tbl, row, 17, f"{self._pct(d_gz, d_cap):.1f}%")
        self._set_num(self.tbl, row, 18, f"{self._pct(d_total, d_cap):.1f}%")

        # Вечер
        e_total = e_pd + e_gz
        self._set_num(self.tbl, row, 19, f"{self._hours(e_pd):.2f}")
        self._set_num(self.tbl, row, 20, f"{self._pct(e_pd, e_cap):.1f}%")
        self._set_num(self.tbl, row, 21, f"{self._hours(e_gz):.2f}")
        self._set_num(self.tbl, row, 22, f"{self._pct(e_gz, e_cap):.1f}%")
        self._set_num(self.tbl, row, 23, f"{self._pct(e_total, e_cap):.1f}%")

        if is_total:
            for c in range(self.tbl.columnCount()):
                it = self.tbl.item(row, c)
                if it:
                    it.setBackground(QColor("#f8fafc"))

    def _bold_font(self) -> QFont:
        f = QFont(self.tbl.font())
        f.setBold(True)
        return f
