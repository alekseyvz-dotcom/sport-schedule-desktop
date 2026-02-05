from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List, Tuple

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
    QToolButton,
)


class TenantRuleDialog(QDialog):
    """
    Диалог правила с выбором зон "плитками".

    - Зоны отображаются как checkable плитки (QToolButton).
    - Разрешён выбор только соседних зон (contiguous) внутри площадки по sort_order.
      Т.е. выбрать можно: Q2 или Q2+Q3 или Q1+Q2+Q3, но нельзя Q1+Q3.
    - Таблица доступности показывает конфликты по всем зонам и кем занято (PD/GZ).
    - Подсветка плиток:
        * зелёная рамка/фон если конфликтов=0
        * красная если конфликтов>0
        * выбранные — с более насыщенной заливкой
    """

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
        self.setObjectName("dialog")
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

        # --- UI: basic rule fields
        self.cmb_venue = QComboBox()
        for vid in sorted(self._venue_label.keys(), key=lambda x: self._venue_label[x]):
            self.cmb_venue.addItem(self._venue_label[vid], vid)

        self.cmb_weekday = QComboBox()
        for k, name in [
            (1, "Понедельник"),
            (2, "Вторник"),
            (3, "Среда"),
            (4, "Четверг"),
            (5, "Пятница"),
            (6, "Суббота"),
            (7, "Воскресенье"),
        ]:
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

        # initial values
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

        # --- Zones tiles
        self.grp_zones = QGroupBox("Зоны (выбираются только соседние)")
        self.zones_grid = QGridLayout(self.grp_zones)
        self.zones_grid.setContentsMargins(10, 10, 10, 10)
        self.zones_grid.setHorizontalSpacing(10)
        self.zones_grid.setVerticalSpacing(10)

        self.btn_select_all = QPushButton("Вся площадка")
        self.btn_clear_all = QPushButton("Снять выбор")
        self.btn_select_all.clicked.connect(self._select_all_zones)
        self.btn_clear_all.clicked.connect(self._clear_all_zones)

        zones_btns = QHBoxLayout()
        zones_btns.addWidget(self.btn_select_all)
        zones_btns.addWidget(self.btn_clear_all)
        zones_btns.addStretch(1)

        self._applying_selection = False

        # unit_id -> button
        self._zone_btns: Dict[int, QToolButton] = {}
        # ordered list of unit_ids for current venue (by sort_order)
        self._venue_unit_order: List[int] = []

        # availability cache: unit_id -> conflict_count
        self._conf_count: Dict[int, int] = {}

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
        self.tbl_avail.setShowGrid(False)
        self.tbl_avail.setAlternatingRowColors(False)
        self.tbl_avail.horizontalHeader().setHighlightSections(False)

        self._avail_timer = QTimer(self)
        self._avail_timer.setSingleShot(True)
        self._avail_timer.setInterval(250)
        self._avail_timer.timeout.connect(self._check_availability)

        # --- Layout
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

        # signals for availability
        self.cmb_venue.currentIndexChanged.connect(self._on_venue_changed)
        self.cmb_weekday.currentIndexChanged.connect(lambda *_: self._schedule_avail_check())
        self.tm_start.timeChanged.connect(lambda *_: self._schedule_avail_check())
        self.tm_end.timeChanged.connect(lambda *_: self._schedule_avail_check())
        self.dt_from.dateChanged.connect(lambda *_: self._schedule_avail_check())
        self.dt_to.dateChanged.connect(lambda *_: self._schedule_avail_check())

        # set initial venue by initial venue_unit_id (edit)
        if "venue_unit_id" in initial and initial["venue_unit_id"]:
            unit_id = int(initial["venue_unit_id"])
            u0 = next((u for u in self._units if int(u["id"]) == unit_id), None)
            if u0:
                vid = int(u0["venue_id"])
                idx = self.cmb_venue.findData(vid)
                if idx >= 0:
                    self.cmb_venue.setCurrentIndex(idx)

        # init venue tiles
        self._on_venue_changed()

        # initial zone selection
        if "venue_unit_ids" in initial and initial["venue_unit_ids"]:
            selected = [int(x) for x in (initial["venue_unit_ids"] or [])]
        elif "venue_unit_id" in initial and initial["venue_unit_id"]:
            selected = [int(initial["venue_unit_id"])]
        else:
            selected = []

        self._apply_selection_contiguous(selected, show_warning=False)
        self._schedule_avail_check()

    # ---------------- Zones tiles ----------------
    def _on_venue_changed(self) -> None:
        vid = int(self.cmb_venue.currentData())

        # clear grid
        for i in reversed(range(self.zones_grid.count())):
            w = self.zones_grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._zone_btns.clear()
        self._conf_count.clear()

        units = self._venue_units_sorted.get(vid, [])
        self._venue_unit_order = [int(u["id"]) for u in units]

        if not units:
            b = QToolButton()
            b.setText("Нет зон")
            b.setEnabled(False)
            self.zones_grid.addWidget(b, 0, 0)
            return

        cols = 4
        for i, u in enumerate(units):
            uid = int(u["id"])
            full = str(u.get("label") or "")
            unit_name = full.split(" — ")[-1].strip() if " — " in full else full

            btn = QToolButton()
            btn.setText(unit_name)
            btn.setCheckable(True)
            btn.setAutoRaise(False)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setMinimumHeight(44)
            btn.setProperty("unit_id", uid)
            btn.toggled.connect(lambda checked, _uid=uid: self._on_tile_toggled(_uid, checked))

            # базовый стиль (дальше будет перекрашиваться по доступности)
            btn.setObjectName("zoneTile")
            btn.setProperty("conflicts", -1)   # -1 = unknown
            btn.setProperty("selected", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

            self._zone_btns[uid] = btn
            self.zones_grid.addWidget(btn, i // cols, i % cols)
            
        self._repaint_tiles()
        self._schedule_avail_check()

        self._apply_selection_contiguous([], show_warning=False)

    def _current_selected_ids(self) -> List[int]:
        ids = [uid for uid, b in self._zone_btns.items() if b.isChecked()]
        # Важно: вернуть в порядке sort_order
        order = {uid: i for i, uid in enumerate(self._venue_unit_order)}
        ids.sort(key=lambda x: order.get(x, 10**9))
        return ids

    @staticmethod
    def _is_contiguous(indices: List[int]) -> bool:
        if not indices:
            return True
        indices = sorted(indices)
        return indices == list(range(indices[0], indices[-1] + 1))

    def _selected_segment(self) -> Tuple[Optional[int], Optional[int]]:
        """
        Возвращает сегмент выбранных зон в индексах sort_order: (l, r) или (None, None).
        """
        sel = self._current_selected_ids()
        if not sel:
            return None, None
        idx_map = {uid: i for i, uid in enumerate(self._venue_unit_order)}
        idxs = [idx_map[uid] for uid in sel if uid in idx_map]
        if not idxs:
            return None, None
        idxs.sort()
        return idxs[0], idxs[-1]

    def _apply_selection_contiguous(self, desired_ids: List[int], *, show_warning: bool) -> None:
        idx_map = {uid: i for i, uid in enumerate(self._venue_unit_order)}
        idxs = [idx_map[uid] for uid in desired_ids if uid in idx_map]
        idxs = sorted(set(idxs))
    
        if not idxs:
            self._applying_selection = True
            try:
                for b in self._zone_btns.values():
                    b.setChecked(False)
            finally:
                self._applying_selection = False
            self._repaint_tiles()
            return
    
        l, r = min(idxs), max(idxs)
        if not self._is_contiguous(idxs):
            if show_warning:
                QMessageBox.information(self, "Зоны", "Можно выбирать только соседние зоны. Выбор будет скорректирован.")
            idxs = list(range(l, r + 1))
    
        selected_ids = {self._venue_unit_order[i] for i in idxs if 0 <= i < len(self._venue_unit_order)}
    
        self._applying_selection = True
        try:
            for uid, b in self._zone_btns.items():
                b.setChecked(uid in selected_ids)
        finally:
            self._applying_selection = False
    
        self._repaint_tiles()


    def _on_tile_toggled(self, uid: int, checked: bool) -> None:
        if getattr(self, "_applying_selection", False):
            return
    
        desired = self._current_selected_ids()
        self._apply_selection_contiguous(desired, show_warning=False)

    def _select_all_zones(self) -> None:
        self._apply_selection_contiguous(list(self._venue_unit_order), show_warning=False)

    def _clear_all_zones(self) -> None:
        self._apply_selection_contiguous([], show_warning=False)

    def _repaint_tiles(self) -> None:
        for uid, btn in self._zone_btns.items():
            conf = self._conf_count.get(uid, -1)  # -1 unknown
            btn.setProperty("conflicts", int(conf))
            btn.setProperty("selected", bool(btn.isChecked()))
    
            # форсим применение QSS по новым property
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    # ---------------- Availability ----------------
    def _schedule_avail_check(self) -> None:
        self._avail_timer.start()

    def _on_avail_row_clicked(self, row: int, col: int) -> None:
        it = self.tbl_avail.item(row, 0)
        if not it:
            return
        uid = it.data(Qt.ItemDataRole.UserRole)
        if uid is None:
            return
        uid = int(uid)
    
        btn = self._zone_btns.get(uid)
        if not btn:
            return

        btn.toggle()

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

            unit_ids = list(self._venue_unit_order)
            if not unit_ids:
                return

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

            # cache conflict counts for tile coloring
            self._conf_count = {int(a.venue_unit_id): int(a.conflict_count) for a in avail}
            self._repaint_tiles()

        except Exception as e:
            self.tbl_avail.setRowCount(0)
            self.tbl_avail.setRowCount(1)
            self.tbl_avail.setItem(0, 0, QTableWidgetItem("—"))
            self.tbl_avail.setItem(0, 1, QTableWidgetItem("—"))
            self.tbl_avail.setItem(0, 2, QTableWidgetItem("—"))
            self.tbl_avail.setItem(0, 3, QTableWidgetItem(f"Ошибка: {type(e).__name__}: {e}"))

    def _fill_availability_table(self, avail) -> None:
        self.tbl_avail.setRowCount(0)

        selected = set(self._current_selected_ids())

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

            if a.conflict_count == 0:
                it_cnt.setForeground(Qt.GlobalColor.darkGreen)
            else:
                it_cnt.setForeground(Qt.GlobalColor.darkRed)

            if int(a.venue_unit_id) in selected:
                for it in (it_zone, it_cnt, it_days, it_who):
                    pass

            self.tbl_avail.setItem(r, 0, it_zone)
            self.tbl_avail.setItem(r, 1, it_cnt)
            self.tbl_avail.setItem(r, 2, it_days)
            self.tbl_avail.setItem(r, 3, it_who)

        self.tbl_avail.resizeColumnsToContents()

    # ---------------- Accept / values ----------------
    def _on_accept(self) -> None:
        if self.tm_end.time() <= self.tm_start.time():
            QMessageBox.warning(self, "Правило", "Время окончания должно быть больше времени начала.")
            return
        if self.dt_to.date() < self.dt_from.date():
            QMessageBox.warning(self, "Правило", "Дата 'по' не может быть раньше даты 'с'.")
            return

        unit_ids = self._current_selected_ids()
        if not unit_ids:
            QMessageBox.warning(self, "Правило", "Выберите хотя бы одну зону.")
            return

        # contiguous-гарантия (на всякий случай)
        idx_map = {uid: i for i, uid in enumerate(self._venue_unit_order)}
        idxs = sorted(idx_map[uid] for uid in unit_ids if uid in idx_map)
        if not self._is_contiguous(idxs):
            QMessageBox.warning(self, "Правило", "Можно выбирать только соседние зоны.")
            return

        self.accept()

    def values(self) -> Dict:
        unit_ids = self._current_selected_ids()
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
