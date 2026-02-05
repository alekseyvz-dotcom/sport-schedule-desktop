from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List

from PySide6.QtCore import QDate, QTime, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
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
)


class TenantRuleDialog(QDialog):
    """
    Диалог создания/редактирования правила.

    Новое:
    - Показывает доступность по всем зонам выбранной площадки на выбранный слот (weekday + time + period).
    - В таблице отображается: конфликтов и пример "кем занято" (PD/GZ).
    """

    def __init__(
        self,
        parent=None,
        *,
        title: str = "Правило расписания",
        venue_units: List[Dict],  # {"id","venue_id","sort_order","label", ...}
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

        # ---- build venues: venue_id -> venue_label; + venue_id -> sorted units
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

        # ---- UI
        self.cmb_venue = QComboBox()
        for vid in sorted(self._venue_label.keys(), key=lambda x: self._venue_label[x]):
            self.cmb_venue.addItem(self._venue_label[vid], vid)

        # Важно: у некоторых площадок может быть не 4 четверти, а 2 половины или 1 main.
        # Но ваш сценарий выбора "сколько четвертей" предполагает линейный набор зон.
        # Поэтому оставляем как есть и подсказываем пользователю через availability-таблицу.
        self.cmb_start_quarter = QComboBox()  # позиция в списке зон (0..3)
        self.cmb_start_quarter.addItem("1", 0)
        self.cmb_start_quarter.addItem("2", 1)
        self.cmb_start_quarter.addItem("3", 2)
        self.cmb_start_quarter.addItem("4", 3)

        self.cmb_quarters = QComboBox()
        self.cmb_quarters.addItem("1/4", 1)
        self.cmb_quarters.addItem("2/4", 2)
        self.cmb_quarters.addItem("3/4", 3)
        self.cmb_quarters.addItem("4/4", 4)

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

        # ---- Availability UI
        self.btn_check = QPushButton("Проверить доступность")
        self.btn_check.clicked.connect(self._check_availability)

        self.tbl_avail = QTableWidget(0, 4)
        self.tbl_avail.setHorizontalHeaderLabels(["Зона", "Конфликтов", "Даты (пример)", "Кем занято (пример)"])
        self.tbl_avail.verticalHeader().setVisible(False)
        self.tbl_avail.setSortingEnabled(False)
        self.tbl_avail.setWordWrap(True)
        self.tbl_avail.horizontalHeader().setStretchLastSection(True)

        self._avail_timer = QTimer(self)
        self._avail_timer.setSingleShot(True)
        self._avail_timer.setInterval(250)
        self._avail_timer.timeout.connect(self._check_availability)

        # defaults from contract
        if contract_valid_from:
            self.dt_from.setDate(QDate(contract_valid_from.year, contract_valid_from.month, contract_valid_from.day))
        else:
            self.dt_from.setDate(QDate.currentDate())

        if contract_valid_to:
            self.dt_to.setDate(QDate(contract_valid_to.year, contract_valid_to.month, contract_valid_to.day))
        else:
            self.dt_to.setDate(QDate.currentDate().addMonths(1))

        # initial (edit)
        if "venue_unit_id" in initial and initial["venue_unit_id"]:
            unit_id = int(initial["venue_unit_id"])
            u0 = next((u for u in self._units if int(u["id"]) == unit_id), None)
            if u0:
                vid = int(u0["venue_id"])
                idx = self.cmb_venue.findData(vid)
                if idx >= 0:
                    self.cmb_venue.setCurrentIndex(idx)

                lst = self._venue_units_sorted.get(vid, [])
                pos = next((i for i, uu in enumerate(lst) if int(uu["id"]) == unit_id), 0)
                self.cmb_start_quarter.setCurrentIndex(max(0, min(3, pos)))

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

        # ---- form
        form = QFormLayout()
        form.addRow("Площадка:", self.cmb_venue)
        form.addRow("С какой зоны (позиция):", self.cmb_start_quarter)
        form.addRow("Сколько зон:", self.cmb_quarters)
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
        root.addWidget(self.btn_check)
        root.addWidget(self.tbl_avail, 1)
        root.addWidget(btns)

        # ---- auto-check scheduling
        self.cmb_venue.currentIndexChanged.connect(lambda *_: self._schedule_avail_check())
        self.cmb_weekday.currentIndexChanged.connect(lambda *_: self._schedule_avail_check())
        self.tm_start.timeChanged.connect(lambda *_: self._schedule_avail_check())
        self.tm_end.timeChanged.connect(lambda *_: self._schedule_avail_check())
        self.dt_from.dateChanged.connect(lambda *_: self._schedule_avail_check())
        self.dt_to.dateChanged.connect(lambda *_: self._schedule_avail_check())

        # initial availability
        self._schedule_avail_check()

    def _schedule_avail_check(self) -> None:
        self._avail_timer.start()

    def _selected_unit_ids(self) -> List[int]:
        vid = int(self.cmb_venue.currentData())
        start_pos = int(self.cmb_start_quarter.currentData())  # 0..3
        need = int(self.cmb_quarters.currentData())            # 1..4

        lst = self._venue_units_sorted.get(vid, [])
        picked = lst[start_pos: start_pos + need]
        if len(picked) != need:
            return []
        return [int(u["id"]) for u in picked]

    def _fill_availability_table(self, avail) -> None:
        self.tbl_avail.setRowCount(0)

        for r, a in enumerate(avail):
            self.tbl_avail.insertRow(r)

            it_zone = QTableWidgetItem(str(getattr(a, "unit_label", "")))
            it_cnt = QTableWidgetItem(str(getattr(a, "conflict_count", 0)))

            days = getattr(a, "conflict_days_sample", []) or []
            days_txt = ", ".join(d.strftime("%d.%m") for d in days)
            it_days = QTableWidgetItem(days_txt)

            who_lines = []
            for c in (getattr(a, "conflicts_sample", []) or [])[:3]:
                # c: SlotConflict(day, starts_at, ends_at, who, ...)
                who_lines.append(f"{c.day:%d.%m} {c.starts_at}-{c.ends_at} — {c.who}")
            it_who = QTableWidgetItem("\n".join(who_lines))

            if int(getattr(a, "conflict_count", 0) or 0) == 0:
                it_cnt.setForeground(Qt.GlobalColor.darkGreen)
            else:
                it_cnt.setForeground(Qt.GlobalColor.darkRed)

            self.tbl_avail.setItem(r, 0, it_zone)
            self.tbl_avail.setItem(r, 1, it_cnt)
            self.tbl_avail.setItem(r, 2, it_days)
            self.tbl_avail.setItem(r, 3, it_who)

        self.tbl_avail.resizeColumnsToContents()

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

            # все зоны выбранной площадки (main либо набор зон)
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

    def _on_accept(self):
        if self.tm_end.time() <= self.tm_start.time():
            QMessageBox.warning(self, "Правило", "Время окончания должно быть больше времени начала.")
            return
        if self.dt_to.date() < self.dt_from.date():
            QMessageBox.warning(self, "Правило", "Дата 'по' не может быть раньше даты 'с'.")
            return

        unit_ids = self._selected_unit_ids()
        need = int(self.cmb_quarters.currentData())
        if len(unit_ids) != need:
            QMessageBox.warning(
                self,
                "Правило",
                "Не удалось подобрать нужное количество зон.\n"
                "Проверьте, что у площадки заведены зоны и корректный sort_order.",
            )
            return

        self.accept()

    def values(self) -> Dict:
        unit_ids = self._selected_unit_ids()
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
