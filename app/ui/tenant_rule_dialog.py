from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List

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
        venue_units: List[Dict],  # ожидаем: {"id","label","venue_id", "sort_order"(опц.)}
        initial: Optional[Dict] = None,
        contract_valid_from: Optional[date] = None,
        contract_valid_to: Optional[date] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self._units = list(venue_units)
        initial = initial or {}

        self.cmb_unit = QComboBox()
        for u in self._units:
            self.cmb_unit.addItem(u["label"], u["id"])

        self.cmb_quarters = QComboBox()
        self.cmb_quarters.addItem("1/4 (одна четверть)", 1)
        self.cmb_quarters.addItem("2/4 (две четверти)", 2)
        self.cmb_quarters.addItem("3/4 (три четверти)", 3)
        self.cmb_quarters.addItem("4/4 (весь зал)", 4)

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

        # apply initial (edit)
        if "venue_unit_id" in initial:
            idx = self.cmb_unit.findData(int(initial["venue_unit_id"]))
            if idx >= 0:
                self.cmb_unit.setCurrentIndex(idx)

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
        form.addRow("Зона (1/4):", self.cmb_unit)
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

    def _on_accept(self):
        if self.tm_end.time() <= self.tm_start.time():
            QMessageBox.warning(self, "Правило", "Время окончания должно быть больше времени начала.")
            return
        if self.dt_to.date() < self.dt_from.date():
            QMessageBox.warning(self, "Правило", "Дата 'по' не может быть раньше даты 'с'.")
            return

        # валидация четвертей: если выбрали 2/4..4/4, проверим что можно подобрать соседние зоны
        unit_ids = self._selected_unit_ids()
        need = int(self.cmb_quarters.currentData())
        if len(unit_ids) != need:
            QMessageBox.warning(
                self,
                "Правило",
                "Не удалось подобрать нужное количество четвертей для выбранной зоны.\n"
                "Проверьте, что у площадки заведены четверти с корректным sort_order.",
            )
            return

        self.accept()

    def _selected_unit_ids(self) -> List[int]:
        """
        Возвращает список venue_unit_id, соответствующих выбранному количеству четвертей.
        Логика: берём выбранный unit и следующие по sort_order внутри той же venue_id.
        """
        base_id = int(self.cmb_unit.currentData())
        need = int(self.cmb_quarters.currentData())

        base = next((u for u in self._units if int(u["id"]) == base_id), None)
        if not base:
            return [base_id]

        venue_id = int(base.get("venue_id")) if base.get("venue_id") is not None else None
        if venue_id is None:
            return [base_id]

        # соберём units этой площадки и отсортируем
        same_venue = [u for u in self._units if int(u.get("venue_id", -1)) == venue_id]
        same_venue.sort(key=lambda u: (int(u.get("sort_order", 0)), str(u.get("label", ""))))

        # найдём позицию base
        pos = next((i for i, u in enumerate(same_venue) if int(u["id"]) == base_id), None)
        if pos is None:
            return [base_id]

        picked = same_venue[pos : pos + need]
        if len(picked) != need:
            return [base_id]  # fallback

        return [int(u["id"]) for u in picked]

    def values(self) -> Dict:
        unit_ids = self._selected_unit_ids()
        return {
            "venue_unit_id": int(unit_ids[0]),          # совместимость со старым кодом
            "venue_unit_ids": unit_ids,                # новое: список
            "weekday": int(self.cmb_weekday.currentData()),
            "starts_at": self.tm_start.time().toPython(),
            "ends_at": self.tm_end.time().toPython(),
            "valid_from": self.dt_from.date().toPython(),
            "valid_to": self.dt_to.date().toPython(),
            "title": self.ed_title.text().strip(),
        }
