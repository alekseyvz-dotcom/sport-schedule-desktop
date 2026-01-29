from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QAbstractItemView,
)

from app.services.ref_service import list_active_orgs, list_active_venues
from app.services.venue_units_service import list_venue_units
from app.services.tenant_rules_service import list_rules_for_tenant, set_rule_active
from app.ui.tenant_rule_dialog import TenantRuleDialog


def _weekday_name(w: int) -> str:
    return ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][int(w)]


class TenantRulesWidget(QWidget):
    """
    Хранит rules в памяти (self._rules_local), чтобы TenantDialog мог вернуть их вызывающему коду.
    Для существующего tenant_id может подтянуть активные правила из БД.
    """

    def __init__(self, parent=None, *, tenant_id: Optional[int], contract_from: Optional[date], contract_to: Optional[date]):
        super().__init__(parent)
        self._tenant_id = tenant_id
        self._contract_from = contract_from
        self._contract_to = contract_to

        self._units = self._load_units_flat()  # список [{"id": unit_id, "label": "...", "venue_id": ...}]
        self._rules_local: List[Dict] = []

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["День", "Время", "Зона", "Период", "Комментарий", "Active"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setStretchLastSection(True)

        self.btn_add = QPushButton("Добавить правило")
        self.btn_edit = QPushButton("Изменить")
        self.btn_del = QPushButton("Отключить")

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_del.clicked.connect(self._on_disable)

        top = QHBoxLayout()
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_del)
        top.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tbl)

        if self._tenant_id:
            self._load_from_db()
        else:
            self._refresh()

    def _load_units_flat(self) -> List[Dict]:
        out: List[Dict] = []
        orgs = list_active_orgs()
        for org in orgs:
            venues = list_active_venues(int(org.id))
            for v in venues:
                units = list_venue_units(int(v.id), include_inactive=False)
                for u in units:
                    out.append(
                        {
                            "id": int(u.id),
                            "venue_id": int(v.id),
                            "label": f"{org.name} / {v.name} — {u.name}",
                        }
                    )
        return out

    def _load_from_db(self):
        rules = list_rules_for_tenant(int(self._tenant_id), include_inactive=True)
        self._rules_local = [
            {
                "id": r.id,
                "weekday": r.weekday,
                "venue_unit_id": r.venue_unit_id,
                "starts_at": r.starts_at,
                "ends_at": r.ends_at,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "title": r.title,
                "is_active": r.is_active,
                "op": "keep",  # keep / new / deactivate
            }
            for r in rules
        ]
        self._refresh()

    def rules_payload(self) -> List[Dict]:
        """
        Возвращает список правил для сохранения вызывающему коду TenantDialog/TenantsPage.
        """
        return list(self._rules_local)

    def _selected_index(self) -> Optional[int]:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        return int(self.tbl.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def _refresh(self):
        self.tbl.setRowCount(0)
        for idx, r in enumerate(self._rules_local):
            self.tbl.insertRow(idx)

            day = QTableWidgetItem(_weekday_name(r["weekday"]))
            day.setData(Qt.ItemDataRole.UserRole, idx)

            tm = QTableWidgetItem(f"{r['starts_at']:%H:%M}–{r['ends_at']:%H:%M}")

            unit_label = next((u["label"] for u in self._units if u["id"] == r["venue_unit_id"]), f"unit_id={r['venue_unit_id']}")
            zone = QTableWidgetItem(unit_label)

            period = QTableWidgetItem(f"{r['valid_from']:%d.%m.%Y}–{r['valid_to']:%d.%m.%Y}")
            title = QTableWidgetItem(r.get("title", "") or "")
            active = QTableWidgetItem("Да" if r.get("is_active", True) and r.get("op") != "deactivate" else "Нет")

            self.tbl.setItem(idx, 0, day)
            self.tbl.setItem(idx, 1, tm)
            self.tbl.setItem(idx, 2, zone)
            self.tbl.setItem(idx, 3, period)
            self.tbl.setItem(idx, 4, title)
            self.tbl.setItem(idx, 5, active)

            if r.get("op") == "deactivate":
                for c in range(6):
                    self.tbl.item(idx, c).setForeground(Qt.GlobalColor.gray)

        self.tbl.resizeColumnsToContents()

    def _on_add(self):
        dlg = TenantRuleDialog(
            self,
            venue_units=self._units,
            contract_valid_from=self._contract_from,
            contract_valid_to=self._contract_to,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        self._rules_local.append(
            {
                "id": None,
                "weekday": v["weekday"],
                "venue_unit_id": v["venue_unit_id"],
                "starts_at": v["starts_at"],
                "ends_at": v["ends_at"],
                "valid_from": v["valid_from"],
                "valid_to": v["valid_to"],
                "title": v["title"],
                "is_active": True,
                "op": "new",
            }
        )
        self._refresh()

    def _on_edit(self):
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return
        r = self._rules_local[idx]
        if r.get("op") == "deactivate":
            QMessageBox.information(self, "Правила", "Правило отключено. Включение сделаем отдельной кнопкой при необходимости.")
            return

        dlg = TenantRuleDialog(
            self,
            title="Изменить правило",
            venue_units=self._units,
            initial=r,
            contract_valid_from=self._contract_from,
            contract_valid_to=self._contract_to,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        v = dlg.values()
        r.update(
            {
                "weekday": v["weekday"],
                "venue_unit_id": v["venue_unit_id"],
                "starts_at": v["starts_at"],
                "ends_at": v["ends_at"],
                "valid_from": v["valid_from"],
                "valid_to": v["valid_to"],
                "title": v["title"],
            }
        )
        # если правило уже было в БД, пока не делаем update в БД (у вас нет update_rule).
        # Здесь самый простой путь: старое отключаем, новое создаём.
        if r.get("id"):
            r["op"] = "deactivate"
            self._rules_local.append(
                {
                    "id": None,
                    "weekday": v["weekday"],
                    "venue_unit_id": v["venue_unit_id"],
                    "starts_at": v["starts_at"],
                    "ends_at": v["ends_at"],
                    "valid_from": v["valid_from"],
                    "valid_to": v["valid_to"],
                    "title": v["title"],
                    "is_active": True,
                    "op": "new",
                }
            )

        self._refresh()
        
    def _on_disable(self):
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return
    
        r = self._rules_local[idx]
    
        # Если правило уже выключено локально — ничего не делаем
        if r.get("op") == "deactivate" or not r.get("is_active", True):
            return
    
        # Если это правило уже в БД — выключаем в БД сразу
        if r.get("id"):
            try:
                set_rule_active(int(r["id"]), False)
            except Exception as e:
                QMessageBox.critical(self, "Правила", f"Не удалось отключить правило:\n{e}")
                return
    
        # Локально тоже помечаем, чтобы TenantDialog вернул актуальный payload
        r["op"] = "deactivate"
        r["is_active"] = False
        self._refresh()

