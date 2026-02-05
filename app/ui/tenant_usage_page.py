# app/ui/tenant_usage_page.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, QTimer, QRectF
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
    QSizePolicy,
)

from app.services.users_service import AuthUser
from app.services.ref_service import list_active_orgs
from app.services.tenant_usage_service import list_usage_by_tenants, TenantUsageRow


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


def _fmt_h(sec: int) -> str:
    return f"{_hours(sec):.1f} ч"


class DonutChart(QWidget):
    """Donut chart: PD vs GZ with center label. Colors from theme-ish palette (dark-friendly)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailsCard")
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._pd = 0
        self._gz = 0
        self._total = 0
        self._title = "Структура"
        self._subtitle = ""

        # dark-friendly defaults (можно потом перенести в theme.py через properties)
        self.col_pd = QColor("#60a5fa")   # blue
        self.col_gz = QColor("#f59e0b")   # amber
        self.col_bg = QColor(255, 255, 255, 28)

        self.col_text = QColor(255, 255, 255, 235)
        self.col_muted = QColor(226, 232, 240, 160)

    def set_data(self, *, pd_sec: int, gz_sec: int, title: str = "Структура", subtitle: str = "") -> None:
        self._pd = int(pd_sec or 0)
        self._gz = int(gz_sec or 0)
        self._total = max(0, self._pd + self._gz)
        self._title = title
        self._subtitle = subtitle
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()

        # title
        p.setPen(self.col_text)
        f = p.font()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(12, 22, self._title)

        # subtitle
        if self._subtitle:
            p.setPen(self.col_muted)
            f2 = p.font()
            f2.setPointSize(9)
            f2.setBold(False)
            p.setFont(f2)
            p.drawText(12, 40, self._subtitle)

        top = 48
        size = min(w - 24, h - top - 12)
        if size < 80:
            return

        rect = QRectF((w - size) / 2, top, size, size)

        pen_bg = QPen(self.col_bg)
        pen_bg.setWidth(max(10, int(size * 0.12)))
        p.setPen(pen_bg)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, 0, 360 * 16)

        if self._total <= 0:
            p.setPen(self.col_muted)
            f3 = p.font()
            f3.setPointSize(10)
            f3.setBold(False)
            p.setFont(f3)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "нет данных")
            return

        start = 90 * 16
        pd_angle = -int(360 * 16 * (self._pd / self._total))
        gz_angle = -int(360 * 16 * (self._gz / self._total))

        pen_pd = QPen(self.col_pd)
        pen_pd.setWidth(pen_bg.width())
        p.setPen(pen_pd)
        p.drawArc(rect, start, pd_angle)

        pen_gz = QPen(self.col_gz)
        pen_gz.setWidth(pen_bg.width())
        p.setPen(pen_gz)
        p.drawArc(rect, start + pd_angle, gz_angle)

        p.setPen(self.col_text)
        fc = p.font()
        fc.setPointSize(12)
        fc.setBold(True)
        p.setFont(fc)
        p.drawText(rect.adjusted(0, -8, 0, -8), Qt.AlignmentFlag.AlignCenter, _fmt_h(self._total))

        p.setPen(self.col_muted)
        fc2 = p.font()
        fc2.setPointSize(9)
        fc2.setBold(False)
        p.setFont(fc2)
        p.drawText(rect.adjusted(0, 28, 0, 28), Qt.AlignmentFlag.AlignCenter, "всего")


class BarListChart(QWidget):
    """Horizontal bars for top tenants with share labels (dark-friendly)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailsCard")
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._title = "Топ контрагентов"
        self._items: List[Tuple[str, int]] = []
        self._total = 0

        self.col_bar = QColor("#60a5fa")
        self.col_bar2 = QColor("#93c5fd")
        self.col_text = QColor(255, 255, 255, 235)
        self.col_muted = QColor(226, 232, 240, 160)
        self.col_bar_bg1 = QColor(255, 255, 255, 18)
        self.col_bar_bg2 = QColor(255, 255, 255, 10)

    def set_data(self, *, title: str, items: List[Tuple[str, int]], total_sec: int) -> None:
        self._title = title
        self._items = list(items or [])
        self._total = int(total_sec or 0)
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()

        p.setPen(self.col_text)
        ft = p.font()
        ft.setPointSize(11)
        ft.setBold(True)
        p.setFont(ft)
        p.drawText(12, 22, self._title)

        top = 38
        left = 12
        right = 12
        bottom = 12
        area_h = h - top - bottom
        if area_h < 80:
            return

        if not self._items or self._total <= 0:
            p.setPen(self.col_muted)
            fm = p.font()
            fm.setPointSize(10)
            fm.setBold(False)
            p.setFont(fm)
            p.drawText(left, top + 24, "нет данных")
            return

        row_h = max(22, min(34, area_h // max(1, len(self._items))))
        bar_h = int(row_h * 0.55)
        gap = row_h - bar_h

        max_val = max(v for _, v in self._items) if self._items else 1

        name_w = int(w * 0.42)
        pct_w = 70
        bar_x0 = left + name_w
        bar_x1 = w - right - pct_w
        bar_w = max(80, bar_x1 - bar_x0)

        fn = p.font()
        fn.setPointSize(9)
        fn.setBold(False)

        for i, (name, val) in enumerate(self._items):
            y = top + i * row_h + gap // 2

            p.setPen(self.col_text)
            p.setFont(fn)
            shown = name[:33] + "…" if len(name) > 36 else name
            p.drawText(
                QRectF(left, y - 2, name_w - 8, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                shown,
            )

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.col_bar_bg1 if i % 2 == 0 else self.col_bar_bg2))
            p.drawRoundedRect(QRectF(bar_x0, y + (row_h - bar_h) / 2, bar_w, bar_h), 6, 6)

            frac = 0.0 if max_val <= 0 else (val / max_val)
            fill_w = max(0.0, bar_w * frac)
            p.setBrush(QBrush(self.col_bar if i == 0 else self.col_bar2))
            p.drawRoundedRect(QRectF(bar_x0, y + (row_h - bar_h) / 2, fill_w, bar_h), 6, 6)

            share = _pct(val, self._total)
            p.setPen(self.col_muted)
            p.drawText(
                QRectF(w - right - pct_w, y - 2, pct_w, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                f"{share:.1f}%",
            )


class TenantUsagePage(QWidget):
    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))
    TOP_N = 10

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

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
        self.cb_only_active = QCheckBox("Только активные контрагенты")
        self.btn_refresh = QPushButton("Обновить")

        self.cmb_org.currentIndexChanged.connect(lambda *_: self.reload())
        self.cmb_period.currentIndexChanged.connect(lambda *_: self.reload())
        self.dt_anchor.dateChanged.connect(lambda *_: self.reload())
        self.cb_cancelled.stateChanged.connect(lambda *_: self.reload())
        self.cb_only_active.stateChanged.connect(lambda *_: self.reload())
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
        top.addWidget(self.cb_only_active)
        top.addWidget(self.btn_refresh)

        self.lbl_period = QLabel("")
        self.lbl_period.setObjectName("scheduleMeta")

        self.lbl_total = QLabel("")
        self.lbl_total.setObjectName("scheduleMetaStrong")

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.addWidget(self.lbl_period, 1)
        meta.addWidget(self.lbl_total, 0, Qt.AlignmentFlag.AlignRight)

        self.chart_donut = DonutChart(self)
        self.chart_top = BarListChart(self)

        charts_row = QHBoxLayout()
        charts_row.setContentsMargins(0, 0, 0, 0)
        charts_row.setSpacing(12)
        charts_row.addWidget(self.chart_donut, 1)
        charts_row.addWidget(self.chart_top, 2)

        self.tbl = QTableWidget(0, 10)
        self.tbl.setObjectName("tenantUsageTable")
        self.tbl.setHorizontalHeaderLabels(
            ["Арендатор", "Тип", "Аренда", "ПД, ч", "ГЗ, ч", "Итого, ч", "Доля", "Доля, %", "Брони", "Отмены"]
        )
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(False)

        header = self.tbl.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(3, 10):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        self.tbl.setColumnWidth(0, 360)
        self.tbl.setColumnWidth(6, 140)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        # card under table
        tbl_card = QWidget(self)
        tbl_card.setObjectName("detailsCard")
        tbl_card_lay = QVBoxLayout(tbl_card)
        tbl_card_lay.setContentsMargins(10, 10, 10, 10)
        tbl_card_lay.setSpacing(0)
        tbl_card_lay.addWidget(self.tbl)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addLayout(meta)
        root.addLayout(charts_row)
        root.addWidget(tbl_card, 1)

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

    @staticmethod
    def _share_bar_text(share_pct: float) -> str:
        n = max(0, min(10, int(round(share_pct / 10.0))))
        return "█" * n + " " * (10 - n)

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
        self.lbl_total.setText(f"ИТОГО: ПД {_hours(total_pd)}ч | ГЗ {_hours(total_gz)}ч | Всего {_hours(total_all)}ч")

        self.chart_donut.set_data(pd_sec=total_pd, gz_sec=total_gz, title="Структура загрузки", subtitle=p.title)

        top_items = sorted(((r.tenant_name, r.total_sec) for r in rows), key=lambda x: x[1], reverse=True)[: self.TOP_N]
        self.chart_top.set_data(title=f"Топ-{min(self.TOP_N, len(top_items))} по часам", items=top_items, total_sec=total_all)

        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(0)

        rows_sorted = sorted(rows, key=lambda r: int(getattr(r, "total_sec", 0)), reverse=True)
        for r in rows_sorted:
            rr = self.tbl.rowCount()
            self.tbl.insertRow(rr)

            share = _pct(r.total_sec, total_all) if total_all > 0 else 0.0

            self.tbl.setItem(rr, 0, QTableWidgetItem(r.tenant_name))
            self.tbl.setItem(rr, 1, QTableWidgetItem(_kind_short(r.tenant_kind)))
            self.tbl.setItem(rr, 2, QTableWidgetItem(_rent_short(r.rent_kind)))
            self.tbl.setItem(rr, 3, QTableWidgetItem(f"{_hours(r.pd_sec):.1f}"))
            self.tbl.setItem(rr, 4, QTableWidgetItem(f"{_hours(r.gz_sec):.1f}"))
            self.tbl.setItem(rr, 5, QTableWidgetItem(f"{_hours(r.total_sec):.1f}"))

            it_bar = QTableWidgetItem(self._share_bar_text(share))
            it_bar.setForeground(QColor(96, 165, 250, 220))
            self.tbl.setItem(rr, 6, it_bar)

            self.tbl.setItem(rr, 7, QTableWidgetItem(f"{share:.1f}%"))
            self.tbl.setItem(rr, 8, QTableWidgetItem(str(r.bookings_count)))
            self.tbl.setItem(rr, 9, QTableWidgetItem(str(r.cancelled_count)))

            for c in (3, 4, 5, 7, 8, 9):
                it = self.tbl.item(rr, c)
                if it:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.tbl.setSortingEnabled(True)
        self.tbl.sortItems(5, Qt.SortOrder.DescendingOrder)
