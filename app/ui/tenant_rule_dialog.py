from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List, Tuple

from PySide6.QtCore import QDate, QTime
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
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._units = list(venue_units)
        initial = initial or {}

        # ---- build venues: venue_id -> venue_label
        self._venue_label: Dict[int, str] = {}
        self._venue_units_sorted: Dict[int, List[Dict]] = {}

        for u in self._units:
            vid = int(u["venue_id"])
            # label вида "Орг / Площадка — Четверть"
            # вытащим "Орг / Площадка" как имя площадки
            base = str(u["label"])
            venue_part = base.split(" — ")[0].strip()
            self._venue_label.setdefault(vid, venue_part)
            self._venue_units_sorted.setdefault(vid, []).append(u)

        for vid, lst in self._venue_units_sorted.items():
            lst.sort(key=lambda x: (int(x.get("sort_order", 0)), str(x.get("label", ""))))

        # ---- UI
        self.cmb_venue = QComboBox()
        for vid in sorted(self._venue_label.keys(), key=lambda x: self._venue_label[x]):
            self.cmb_venue.addItem(self._venue_label[vid], vid)

        self.cmb_start_quarter = QComboBox()  # 1..4 по sort_order
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

                # позиция четверти в sort_order списке
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

        form = QFormLayout()
        form.addRow("Площадка:", self.cmb_venue)
        form.addRow("С какой четверти:", self.cmb_start_quarter)
        form.addRow("Сколько четвертей:", self.cmb_quarters)
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
        root.addWidget(btns)

    def _selected_unit_ids(self) -> List[int]:
        vid = int(self.cmb_venue.currentData())
        start_pos = int(self.cmb_start_quarter.currentData())  # 0..3
        need = int(self.cmb_quarters.currentData())            # 1..4

        lst = self._venue_units_sorted.get(vid, [])
        picked = lst[start_pos : start_pos + need]
        if len(picked) != need:
            return []
        return [int(u["id"]) for u in picked]

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
                "Не удалось подобрать нужное количество четвертей.\n"
                "Проверьте, что у площадки заведены 4 четверти и корректный sort_order.",
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
