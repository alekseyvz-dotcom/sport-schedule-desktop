from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
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

        self.tbl = QTableWidget(0, 12)
        self.tbl.setHorizontalHeaderLabels(
            [
                "Учреждение",
                "Площадка",
                "Доступно, ч",
                "PD, ч",
                "PD, %",
                "GZ, ч",
                "GZ, %",
                "Итого, ч",
                "Итого, %",
                "Утро (08-12), ч",
                "День (12-18), ч",
                "Вечер (18-22), ч",
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
        for c in range(2, 12):
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
            # сохранить первый пункт "Все"
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
            # ISO: понедельник
            start = d - timedelta(days=d.weekday())
            end = start + timedelta(days=6)
            return Period(start=start, end=end, title=f"Неделя: {start:%d.%m.%Y} – {end:%d.%m.%Y}")
        if mode == "month":
            start = d.replace(day=1)
            if start.month == 12:
                next_month = start.replace(year=start.year + 1, month=1, day=1)
            else:
                next_month = start.replace(month=start.month + 1, day=1)
            end = next_month - timedelta(days=1)
            return Period(start=start, end=end, title=f"Месяц: {start:%m.%Y} ({start:%d.%m.%Y} – {end:%d.%m.%Y})")
        if mode == "quarter":
            q = (d.month - 1) // 3 + 1
            start_month = 3 * (q - 1) + 1
            start = d.replace(month=start_month, day=1)
            # следующий квартал
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

    @staticmethod
    def _hours(sec: int) -> float:
        return round(sec / 3600.0, 2)

    @staticmethod
    def _pct(sec: int, cap: int) -> float:
        if cap <= 0:
            return 0.0
        return round(100.0 * (sec / cap), 1)

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

        # totals
        cap = sum(r.capacity_sec for r in rows)
        pd = sum(r.pd_sec for r in rows)
        gz = sum(r.gz_sec for r in rows)
        tot = pd + gz
        self.lbl_total.setText(
            f"ИТОГО: PD {self._hours(pd)}ч ({self._pct(pd, cap)}%) | "
            f"GZ {self._hours(gz)}ч ({self._pct(gz, cap)}%) | "
            f"Занято {self._hours(tot)}ч ({self._pct(tot, cap)}%)"
        )

        self.tbl.setRowCount(0)
        self.tbl.setSortingEnabled(False)

        for r in rows:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)

            cap_h = self._hours(r.capacity_sec)
            pd_h = self._hours(r.pd_sec)
            gz_h = self._hours(r.gz_sec)
            tot_h = self._hours(r.total_sec)

            pd_pct = self._pct(r.pd_sec, r.capacity_sec)
            gz_pct = self._pct(r.gz_sec, r.capacity_sec)
            tot_pct = self._pct(r.total_sec, r.capacity_sec)

            items = [
                QTableWidgetItem(r.org_name),
                QTableWidgetItem(r.venue_name),
                QTableWidgetItem(f"{cap_h:.2f}"),
                QTableWidgetItem(f"{pd_h:.2f}"),
                QTableWidgetItem(f"{pd_pct:.1f}%"),
                QTableWidgetItem(f"{gz_h:.2f}"),
                QTableWidgetItem(f"{gz_pct:.1f}%"),
                QTableWidgetItem(f"{tot_h:.2f}"),
                QTableWidgetItem(f"{tot_pct:.1f}%"),
                QTableWidgetItem(f"{self._hours(r.morning_sec):.2f}"),
                QTableWidgetItem(f"{self._hours(r.day_sec):.2f}"),
                QTableWidgetItem(f"{self._hours(r.evening_sec):.2f}"),
            ]

            for c, it in enumerate(items):
                if c >= 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl.setItem(row, c, it)

            # слегка подсветим высокую загрузку
            if tot_pct >= 80:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(row, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkRed)
            elif tot_pct >= 60:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(row, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkBlue)

        # сортировка по "Итого, %" (колонка 8) по убыванию — вручную
        self._sort_by_total_percent_desc()

        self.tbl.resizeRowsToContents()

    def _sort_by_total_percent_desc(self):
        # простая сортировка таблицы без включения встроенного sort (проценты как строка)
        rows_data = []
        for r in range(self.tbl.rowCount()):
            pct_text = self.tbl.item(r, 8).text().replace("%", "").strip()
            try:
                pct = float(pct_text)
            except Exception:
                pct = 0.0
            row_items = [self.tbl.takeItem(r, c) for c in range(self.tbl.columnCount())]
            rows_data.append((pct, row_items))

        rows_data.sort(key=lambda x: x[0], reverse=True)

        self.tbl.setRowCount(0)
        for pct, items in rows_data:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            for c, it in enumerate(items):
                self.tbl.setItem(row, c, it)
