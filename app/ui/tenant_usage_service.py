from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

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
)

from app.services.users_service import AuthUser
from app.services.ref_service import list_active_orgs
from app.services.tenant_usage_service import list_usage_by_tenants, TenantUsageRow


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


def _hours(sec: int) -> float:
    return round(sec / 3600.0, 1)


def _pct(sec: int, cap: int) -> float:
    return 0.0 if cap <= 0 else 100.0 * (sec / cap)


def _kind_short(k: str) -> str:
    return "ФЛ" if (k or "") == "person" else ("ЮЛ" if (k or "") == "legal" else "—")


def _rent_short(r: str) -> str:
    if (r or "") == "one_time":
        return "Разово"
    if (r or "") == "long_term":
        return "Долгоср."
    return "—"


class TenantUsagePage(QWidget):
    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_PAGE_QSS)
        self._user = user
        self._period: Optional[Period] = None
        self._rows: List[TenantUsageRow] = []

        self.lbl_title = QLabel("Загрузка арендаторов")
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

        self.cb_only_active = QCheckBox("Только активные контрагенты")
        self.cb_only_active.setChecked(False)

        self.btn_refresh = QPushButton("Обновить")

        self.cmb_org.currentIndexChanged.connect(lambda *_: self.reload())
        self.cmb_period.currentIndexChanged.connect(lambda *_: self.reload())
        self.dt_anchor.dateChanged.connect(lambda *_: self.reload())
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())
        self.cb_only_active.stateChanged.connect(lambda *_: self.reload())
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
        top.addWidget(self.cb_only_active)
        top.addWidget(self.btn_refresh)

        self.lbl_period = QLabel("")
        self.lbl_period.setStyleSheet("color:#334155; padding:0 4px;")

        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("color:#0f172a; font-weight:600; padding:0 4px;")

        meta = QHBoxLayout()
        meta.setContentsMargins(12, 0, 12, 0)
        meta.addWidget(self.lbl_period, 1)
        meta.addWidget(self.lbl_total, 0, Qt.AlignmentFlag.AlignRight)

        self.tbl = QTableWidget(0, 9)
        self.tbl.setHorizontalHeaderLabels(
            [
                "Арендатор",
                "Тип",
                "Аренда",
                "ПД, ч",
                "ГЗ, ч",
                "Итого, ч",
                "Доля, %",
                "Брони",
                "Отмены",
            ]
        )
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)

        header = self.tbl.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 9):
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
            QMessageBox.critical(self, "Загрузка арендаторов", f"Ошибка загрузки учреждений:\n{e}")
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
            next_month = start.replace(year=start.year + 1, month=1, day=1) if start.month == 12 else start.replace(month=start.month + 1, day=1)
            end = next_month - timedelta(days=1)
            return Period(start=start, end=end, title=f"Месяц: {start:%m.%Y} ({start:%d.%m.%Y} – {end:%d.%m.%Y})")
        if mode == "quarter":
            q = (d.month - 1) // 3 + 1
            start_month = 3 * (q - 1) + 1
            start = d.replace(month=start_month, day=1)
            next_q = start.replace(year=start.year + 1, month=1, day=1) if start_month == 10 else start.replace(month=start_month + 3, day=1)
            end = next_q - timedelta(days=1)
            return Period(start=start, end=end, title=f"Квартал Q{q}: {start:%d.%m.%Y} – {end:%d.%m.%Y}")
        if mode == "year":
            start = d.replace(month=1, day=1)
            end = d.replace(month=12, day=31)
            return Period(start=start, end=end, title=f"Год: {d.year}")
        return Period(start=d, end=d, title=f"{d:%d.%m.%Y}")

    def reload(self):
        p = self._calc_period()
        self._period = p
        self.lbl_period.setText(f"Период: {p.title}")

        org_id = self.cmb_org.currentData()
        include_cancelled = self.cb_cancelled.isChecked()
        only_active = self.cb_only_active.isChecked()

        start_dt = datetime.combine(p.start, datetime.min.time(), tzinfo=self.TZ)
        end_dt = datetime.combine(p.end + timedelta(days=1), datetime.min.time(), tzinfo=self.TZ)

        try:
            rows = list_usage_by_tenants(
                start_dt=start_dt,
                end_dt=end_dt,
                org_id=(int(org_id) if org_id is not None else None),
                include_cancelled=include_cancelled,
                only_active_tenants=only_active,
            )
        except Exception as e:
            QMessageBox.critical(self, "Загрузка арендаторов", f"Ошибка расчёта:\n{e}")
            return

        self._rows = list(rows)

        total_pd = sum(r.pd_sec for r in rows)
        total_gz = sum(r.gz_sec for r in rows)
        total_all = total_pd + total_gz
        self.lbl_total.setText(
            f"ИТОГО: ПД {_hours(total_pd)}ч | ГЗ {_hours(total_gz)}ч | Всего {_hours(total_all)}ч"
        )

        self.tbl.setRowCount(0)

        for r in rows:
            rr = self.tbl.rowCount()
            self.tbl.insertRow(rr)

            share = _pct(r.total_sec, total_all) if total_all > 0 else 0.0

            self.tbl.setItem(rr, 0, QTableWidgetItem(r.tenant_name))
            self.tbl.setItem(rr, 1, QTableWidgetItem(_kind_short(r.tenant_kind)))
            self.tbl.setItem(rr, 2, QTableWidgetItem(_rent_short(r.rent_kind)))
            self.tbl.setItem(rr, 3, QTableWidgetItem(f"{_hours(r.pd_sec):.1f}"))
            self.tbl.setItem(rr, 4, QTableWidgetItem(f"{_hours(r.gz_sec):.1f}"))
            self.tbl.setItem(rr, 5, QTableWidgetItem(f"{_hours(r.total_sec):.1f}"))
            self.tbl.setItem(rr, 6, QTableWidgetItem(f"{share:.1f}%"))
            self.tbl.setItem(rr, 7, QTableWidgetItem(str(r.bookings_count)))
            self.tbl.setItem(rr, 8, QTableWidgetItem(str(r.cancelled_count)))

            for c in (3, 4, 5, 6, 7, 8):
                it = self.tbl.item(rr, c)
                if it:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
