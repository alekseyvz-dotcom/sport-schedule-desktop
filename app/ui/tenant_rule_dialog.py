from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List

from PySide6.QtCore import QDate, QTime, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QComboBox,
    QTimeEdit,
    QDateEdit,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QGroupBox,
    QGridLayout,
    QCheckBox,
)


class TenantRuleDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str = "Правило расписания",
        venue_units: List[Dict],  # {"id","venue_id","sort_order","label"}
        initial: Optional[Dict] = None,
        contract_valid_from: Optional[date] = None,
        contract_valid_to: Optional[date] = None,
        tz_name: str = "Europe/Moscow",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._units = list(venue_units)
        self._tz_name = tz_name
        initial = initial or {}

        # venue_id -> label ; venue_id -> units[]
        self._venue_label: Dict[int, str] = {}
        self._venue_units_sorted: Dict[int, List[Dict]] = {}

        for u in self._units:
            vid = int(u["venue_id"])
            base = str(u.get("label") or "")
            venue_part = base.split(" — ")[0].strip() or f"venue_id={vid}"
            self._venue_label.setdefault(vid, venue_part)
            self._venue_units_sorted.setdefault(vid, []).append(u)

        for vid, lst in self._venue_units_sorted.items():
            lst.sort(key=lambda x: (int(x.get("sort_order", 0)), str(x.get("label", ""))))

        # --- UI
        self.cmb_venue = QComboBox()
        for vid in sorted(self._venue_label.keys(), key=lambda x: self._venue_label[x]):
            self.cmb_venue.addItem(self._venue_label[vid], vid)

        self.cmb_weekday = QComboBox()
        days = [
            (1, "Понедельник"),
            (2, "Вторник"),
            (3, "Среда"),
            (4, "Четверг"),
            (5, "Пятница"),
            (6, "Суббота"),
            (7, "Воскресенье"),
        ]
        for k, name in days:
            self.cmb_weekday.addItem(name, k)

        self.tm_start = QTimeEdit()
        self.tm_end = QTimeEdit()
        self.tm_start.setDisplayFormat("HH:mm")
        self.tm_end.setDisplayFormat("HH:mm")

        self.dt_from = QDateEdit()
        self.dt_to = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_to.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("dd.MM.yyyy")
        self.dt_to.setDisplayFormat("dd.MM.yyyy")

        self.ed_title = QLineEdit()

        # defaults from contract
        if contract_valid_from:
            self.dt_from.setDate(QDate(contract_valid_from.year, contract_valid_from.month, contract_valid_from.day))
        else:
            self.dt_from.setDate(QDate.currentDate())

        if contract_valid_to:
            self.dt_to.setDate(QDate(contract_valid_to.year, contract_valid_to.month, contract_valid_to.day))
        else:
            self.dt_to.setDate(QDate.currentDate().addMonths(1))

        # initial values (edit)
        if "weekday" in initial:
            idx = self.cmb_weekday.findData(int(initial["weekday"]))
            if idx >= 0:
                self.cmb_weekday.setCurrentIndex(idx)

        if "starts_at" in initial:
            self.tm_start.setTime(QTime.fromString(str(initial["starts_at"])[:5], "HH:mm"))
        else:
            self.tm_start.setTime(QTime(12, 0))

        if "ends_at" in initial:
            self.tm_end.setTime(QTime.fromString(str(initial["ends_at"])[:5], "HH:mm"))
        else:
            self.tm_end.setTime(QTime(14, 0))

        if "valid_from" in initial and initial["valid_from"]:
            d = initial["valid_from"]
            self.dt_from.setDate(QDate(d.year, d.month, d.day))
        if "valid_to" in initial and initial["valid_to"]:
            d = initial["valid_to"]
            self.dt_to.setDate(QDate(d.year, d.month, d.day))

        self.ed_title.setText(initial.get("title", "") or "")

        # --- Zones block
        self.grp_zones = QGroupBox("Зоны")
        self.zones_grid = QGridLayout(self.grp_zones)
        self.zones_grid.setContentsMargins(10, 10, 10, 10)
        self.zones_grid.setHorizontalSpacing(12)
        self.zones_grid.setVerticalSpacing(6)

        self._zone_checks: Dict[int, QCheckBox] = {}  # unit_id -> checkbox

        self.btn_select_all = QPushButton("Выбрать все")
        self.btn_clear_all = QPushButton("Снять все")
        self.btn_select_all.clicked.connect(self._select_all_zones)
        self.btn_clear_all.clicked.connect(self._clear_all_zones)

        zones_btns = QHBoxLayout()
        zones_btns.addWidget(self.btn_select_all)
        zones_btns.addWidget(self.btn_clear_all)
        zones_btns.addStretch(1)

        # --- Availability UI
        self.btn_check = QPushButton("Проверить доступность")
        self.btn_check.clicked.connect(self._check_availability)

        self.tbl_avail = QTableWidget(0, 4)
        self.tbl_avail.setHorizontalHeaderLabels(["Зона", "Конфликтов", "Даты (пример)", "Кем занято (пример)"])
        self.tbl_avail.verticalHeader().setVisible(False)
        self.tbl_avail.setSortingEnabled(False)
        self.tbl_avail.setWordWrap(True)
        self.tbl_avail.horizontalHeader().setStretchLastSection(True)
        self.tbl_avail.cellClicked.connect(self._on_avail_row_clicked)

        self._avail_timer = QTimer(self)
        self._avail_timer.setSingleShot(True)
        self._avail_timer.setInterval(250)
        self._avail_timer.timeout.connect(self._check_availability)

        # --- Form layout
        form = QFormLayout()
        form.addRow("Площадка:", self.cmb_venue)
        form.addRow("День недели:", self.cmb_weekday)
        form.addRow("Начало:", self.tm_start)
        form.addRow("Окончание:", self.tm_end)
        form.addRow("Действует с:", self.dt_from)
        form.addRow("Действует по:", self.dt_to)
        form.addRow("Комментарий:", self.ed_title)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(zones_btns)
        root.addWidget(self.grp_zones)
        root.addWidget(self.btn_check)
        root.addWidget(self.tbl_avail, 1)
        root.addWidget(btns)

        # signals
        self.cmb_venue.currentIndexChanged.connect(self._on_venue_changed)
        self.cmb_weekday.currentIndexChanged.connect(lambda *_: self._schedule_avail_check())
        self.tm_start.timeChanged.connect(lambda *_: self._schedule_avail_check())
        self.tm_end.timeChanged.connect(lambda *_: self._schedule_avail_check())
        self.dt_from.dateChanged.connect(lambda *_: self._schedule_avail_check())
        self.dt_to.dateChanged.connect(lambda *_: self._schedule_avail_check())

        # set initial venue by initial venue_unit_id (если редактирование)
        if "venue_unit_id" in initial and initial["venue_unit_id"]:
            unit_id = int(initial["venue_unit_id"])
            u0 = next((u for u in self._units if int(u["id"]) == unit_id), None)
            if u0:
                vid = int(u0["venue_id"])
                idx = self.cmb_venue.findData(vid)
                if idx >= 0:
                    self.cmb_venue.setCurrentIndex(idx)

        # init zones for current venue
        self._on_venue_changed()

        # initial zone selection
        if "venue_unit_ids" in initial and initial["venue_unit_ids"]:
            selected = {int(x) for x in (initial["venue_unit_ids"] or [])}
        elif "venue_unit_id" in initial and initial["venue_unit_id"]:
            selected = {int(initial["venue_unit_id"])}
        else:
            selected = set()

        for uid, cb in self._zone_checks.items():
            cb.setChecked(uid in selected)

        self._schedule_avail_check()

    # ---------- zones ----------
    def _on_venue_changed(self) -> None:
        vid = int(self.cmb_venue.currentData())

        # пересоздать список чекбоксов
        for i in reversed(range(self.zones_grid.count())):
            w = self.zones_grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._zone_checks.clear()

        units = self._venue_units_sorted.get(vid, [])
        if not units:
            lbl = QCheckBox("Нет зон")
            lbl.setEnabled(False)
            self.zones_grid.addWidget(lbl, 0, 0)
            return

        # раскладываем плиткой 4 в ряд (можно менять)
        cols = 4
        for i, u in enumerate(units):
            uid = int(u["id"])
            # label вида "Орг / Площадка — Q1" → нам нужно "Q1"
            full = str(u.get("label") or "")
            unit_name = full.split(" — ")[-1].strip() if " — " in full else full

            cb = QCheckBox(unit_name)
            cb.stateChanged.connect(lambda *_: self._schedule_avail_check())
            self._zone_checks[uid] = cb

            self.zones_grid.addWidget(cb, i // cols, i % cols)

        self._schedule_avail_check()

    def _select_all_zones(self) -> None:
        for cb in self._zone_checks.values():
            cb.setChecked(True)

    def _clear_all_zones(self) -> None:
        for cb in self._zone_checks.values():
            cb.setChecked(False)

    def _selected_unit_ids(self) -> List[int]:
        picked = [uid for uid, cb in self._zone_checks.items() if cb.isChecked()]
        picked.sort()
        return picked

    # ---------- availability ----------
    def _schedule_avail_check(self) -> None:
        self._avail_timer.start()

    def _on_avail_row_clicked(self, row: int, col: int) -> None:
        # клик по строке таблицы доступности переключает соответствующую зону
        it = self.tbl_avail.item(row, 0)
        if not it:
            return
        uid = it.data(Qt.ItemDataRole.UserRole)
        if uid is None:
            return
        uid = int(uid)
        cb = self._zone_checks.get(uid)
        if cb:
            cb.setChecked(not cb.isChecked())

    def _check_availability(self) -> None:
        try:
            vid = int(self.cmb_venue.currentData())
            weekday = int(self.cmb_weekday.currentData())
            starts = self.tm_start.time().toPython()
            ends = self.tm_end.time().toPython()
            valid_from = self.dt_from.date().toPython()
            valid_to = self.dt_to.date().toPython()

            if ends <= starts or valid_to < valid_from:
                return

            # проверяем все зоны площадки (а не только выбранные) — чтобы пользователь видел картину
            units = self._venue_units_sorted.get(vid, [])
            unit_ids = [int(u["id"]) for u in units]

            from app.services.availability_service import get_units_availability_for_rule

            avail = get_units_availability_for_rule(
                venue_id=vid,
                venue_unit_ids=unit_ids,
                weekday=weekday,
                starts_at=starts,
                ends_at=ends,
                valid_from=valid_from,
                valid_to=valid_to,
                tz_name=self._tz_name,
            )
            self._fill_availability_table(avail)

        except Exception as e:
            self.tbl_avail.setRowCount(0)
            self.tbl_avail.setRowCount(1)
            self.tbl_avail.setItem(0, 0, QTableWidgetItem("—"))
            self.tbl_avail.setItem(0, 1, QTableWidgetItem("—"))
            self.tbl_avail.setItem(0, 2, QTableWidgetItem("—"))
            self.tbl_avail.setItem(0, 3, QTableWidgetItem(f"Ошибка: {type(e).__name__}: {e}"))

    def _fill_availability_table(self, avail) -> None:
        self.tbl_avail.setRowCount(0)

        selected = set(self._selected_unit_ids())

        for r, a in enumerate(avail):
            self.tbl_avail.insertRow(r)

            it_zone = QTableWidgetItem(str(a.unit_label))
            it_zone.setData(Qt.ItemDataRole.UserRole, int(a.venue_unit_id))

            it_cnt = QTableWidgetItem(str(a.conflict_count))

            days_txt = ", ".join(d.strftime("%d.%m") for d in (a.conflict_days_sample or []))
            it_days = QTableWidgetItem(days_txt)

            who_lines = []
            for c in (a.conflicts_sample or [])[:3]:
                who_lines.append(f"{c.day:%d.%m} {c.starts_at}-{c.ends_at} — {c.who}")
            it_who = QTableWidgetItem("\n".join(who_lines))

            # подсветка конфликтов
            if a.conflict_count == 0:
                it_cnt.setForeground(Qt.GlobalColor.darkGreen)
            else:
                it_cnt.setForeground(Qt.GlobalColor.darkRed)

            # подсветка выбранных зон
            if int(a.venue_unit_id) in selected:
                for it in (it_zone, it_cnt, it_days, it_who):
                    it.setBackground(Qt.GlobalColor.lightGray)

            self.tbl_avail.setItem(r, 0, it_zone)
            self.tbl_avail.setItem(r, 1, it_cnt)
            self.tbl_avail.setItem(r, 2, it_days)
            self.tbl_avail.setItem(r, 3, it_who)

        self.tbl_avail.resizeColumnsToContents()

    # ---------- accept/values ----------
    def _on_accept(self) -> None:
        if self.tm_end.time() <= self.tm_start.time():
            QMessageBox.warning(self, "Правило", "Время окончания должно быть больше времени начала.")
            return
        if self.dt_to.date() < self.dt_from.date():
            QMessageBox.warning(self, "Правило", "Дата 'по' не может быть раньше даты 'с'.")
            return

        unit_ids = self._selected_unit_ids()
        if not unit_ids:
            QMessageBox.warning(self, "Правило", "Выберите хотя бы одну зону.")
            return

        self.accept()

    def values(self) -> Dict:
        unit_ids = self._selected_unit_ids()
        # venue_unit_id оставим как первый элемент для совместимости со старым кодом
        return {
            "venue_unit_id": int(unit_ids[0]),
            "venue_unit_ids": unit_ids,
            "weekday": int(self.cmb_weekday.currentData()),
            "starts_at": self.tm_start.time().toPython(),
            "ends_at": self.tm_end.time().toPython(),
            "valid_from": self.dt_from.date().toPython(),
            "valid_to": self.dt_to.date().toPython(),
            "title": self.ed_title.text().strip(),
        }
