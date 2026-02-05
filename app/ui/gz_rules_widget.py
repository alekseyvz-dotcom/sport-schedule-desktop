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
    QHeaderView,
)

from app.services.ref_service import list_active_orgs, list_active_venues
from app.services.venue_units_service import list_venue_units
from app.services.gz_rules_service import (
    list_rules_for_group,
    set_rule_active,
    delete_rule,
)
from app.services.bookings_service import cancel_future_gz_bookings_like_rule
from app.ui.tenant_rule_dialog import TenantRuleDialog


def _weekday_name(w: int) -> str:
    return ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][int(w)]


class GzRulesWidget(QWidget):
    def __init__(
        self,
        parent=None,
        *,
        gz_group_id: Optional[int],
        is_admin: bool = False,
        group_period_from: Optional[date] = None,
        group_period_to: Optional[date] = None,
        user_id: int,
        role_code: str,
    ):
        super().__init__(parent)
        self.setObjectName("page")  # чтобы на случай отдельного показа был нормальный фон

        self._gz_group_id = gz_group_id
        self._is_admin = bool(is_admin)

        self._user_id = int(user_id)
        self._role_code = str(role_code or "")

        self._group_period_from: Optional[date] = group_period_from
        self._group_period_to: Optional[date] = group_period_to

        self._units = self._load_units_flat()
        self._rules_local: List[Dict] = []

        self.tbl = QTableWidget(0, 6)
        self.tbl.setObjectName("gzRulesTable")
        self.tbl.setHorizontalHeaderLabels(["День", "Время", "Зона", "Период", "Комментарий", "Активно"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setShowGrid(False)
        self.tbl.setAlternatingRowColors(False)

        hdr = self.tbl.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.btn_add = QPushButton("Добавить правило")
        self.btn_edit = QPushButton("Изменить")
        self.btn_disable = QPushButton("Отключить")
        self.btn_delete = QPushButton("Удалить правило")
        self.btn_delete.setVisible(self._is_admin)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_disable.clicked.connect(self._on_disable)
        self.btn_delete.clicked.connect(self._on_delete)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_disable)
        if self._is_admin:
            top.addWidget(self.btn_delete)
        top.addStretch(1)

        # карточка под таблицу (единый фон как у виджетов)
        table_card = QWidget(self)
        table_card.setObjectName("detailsCard")
        card_lay = QVBoxLayout(table_card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        card_lay.setSpacing(0)
        card_lay.addWidget(self.tbl)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(table_card, 1)

        if self._gz_group_id:
            self._load_from_db()
        else:
            self._refresh()

    def set_group_period(self, period_from: Optional[date], period_to: Optional[date]) -> None:
        self._group_period_from = period_from
        self._group_period_to = period_to

    def _default_rule_title(self) -> str:
        return "ГЗ"

    def _load_units_flat(self) -> List[Dict]:
        out: List[Dict] = []
        orgs = list_active_orgs()
        for org in orgs:
            venues = list_active_venues(int(org.id))
            for v in venues:
                units = list_venue_units(int(v.id), include_inactive=False)

                if units:
                    for u in units:
                        out.append(
                            {
                                "id": int(u.id),
                                "venue_id": int(v.id),
                                "sort_order": int(getattr(u, "sort_order", 0)),
                                "label": f"{org.name} / {v.name} — {u.name}",
                            }
                        )
                else:
                    out.append(
                        {
                            "id": -int(v.id),
                            "venue_id": int(v.id),
                            "sort_order": 0,
                            "label": f"{org.name} / {v.name} — (без зон)",
                        }
                    )
        return out

    def _load_from_db(self):
        rules = list_rules_for_group(
            user_id=self._user_id,
            role_code=self._role_code,
            gz_group_id=int(self._gz_group_id),
            include_inactive=True,
        )
        self._rules_local = [
            {
                "id": int(r.id),
                "weekday": int(r.weekday),
                "venue_unit_id": int(r.venue_unit_id),
                "starts_at": r.starts_at,
                "ends_at": r.ends_at,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "title": r.title,
                "is_active": bool(r.is_active),
                "op": "keep",
            }
            for r in rules
        ]
        self._refresh()

    def rules_payload(self) -> List[Dict]:
        return list(self._rules_local)

    def _selected_index(self) -> Optional[int]:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        return int(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _refresh(self):
        self.tbl.setRowCount(0)
        for idx, r in enumerate(self._rules_local):
            self.tbl.insertRow(idx)

            day = QTableWidgetItem(_weekday_name(r["weekday"]))
            day.setData(Qt.ItemDataRole.UserRole, idx)

            tm = QTableWidgetItem(f"{r['starts_at']:%H:%M}–{r['ends_at']:%H:%M}")

            unit_label = next(
                (u["label"] for u in self._units if u["id"] == r["venue_unit_id"]),
                f"unit_id={r['venue_unit_id']}",
            )
            zone = QTableWidgetItem(unit_label)

            period = QTableWidgetItem(f"{r['valid_from']:%d.%m.%Y}–{r['valid_to']:%d.%m.%Y}")
            title = QTableWidgetItem(r.get("title", "") or "")

            is_active = bool(r.get("is_active", True)) and r.get("op") != "deactivate"
            active = QTableWidgetItem("Да" if is_active else "Нет")
            active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(idx, 0, day)
            self.tbl.setItem(idx, 1, tm)
            self.tbl.setItem(idx, 2, zone)
            self.tbl.setItem(idx, 3, period)
            self.tbl.setItem(idx, 4, title)
            self.tbl.setItem(idx, 5, active)

            if r.get("op") == "deactivate" or not r.get("is_active", True):
                for c in range(self.tbl.columnCount()):
                    item = self.tbl.item(idx, c)
                    if item:
                        item.setForeground(Qt.GlobalColor.gray)

        self.tbl.resizeColumnsToContents()

    def _on_add(self):
        dlg = TenantRuleDialog(
            self,
            venue_units=self._units,
            contract_valid_from=self._group_period_from,
            contract_valid_to=self._group_period_to,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        v = dlg.values()
        unit_ids = v.get("venue_unit_ids") or [v["venue_unit_id"]]
        title = (v.get("title") or "").strip() or self._default_rule_title()

        for uid in unit_ids:
            self._rules_local.append(
                {
                    "id": None,
                    "weekday": v["weekday"],
                    "venue_unit_id": int(uid),
                    "starts_at": v["starts_at"],
                    "ends_at": v["ends_at"],
                    "valid_from": v["valid_from"],
                    "valid_to": v["valid_to"],
                    "title": title,
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
        if r.get("op") == "deactivate" or not r.get("is_active", True):
            QMessageBox.information(self, "Правила", "Правило отключено.")
            return

        dlg = TenantRuleDialog(
            self,
            title="Изменить правило",
            venue_units=self._units,
            initial=r,
            contract_valid_from=self._group_period_from,
            contract_valid_to=self._group_period_to,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        v = dlg.values()
        title = (v.get("title") or "").strip() or self._default_rule_title()

        if r.get("id"):
            r["op"] = "deactivate"
            r["is_active"] = False

            self._rules_local.append(
                {
                    "id": None,
                    "weekday": v["weekday"],
                    "venue_unit_id": v["venue_unit_id"],
                    "starts_at": v["starts_at"],
                    "ends_at": v["ends_at"],
                    "valid_from": v["valid_from"],
                    "valid_to": v["valid_to"],
                    "title": title,
                    "is_active": True,
                    "op": "new",
                }
            )
        else:
            r.update(
                {
                    "weekday": v["weekday"],
                    "venue_unit_id": v["venue_unit_id"],
                    "starts_at": v["starts_at"],
                    "ends_at": v["ends_at"],
                    "valid_from": v["valid_from"],
                    "valid_to": v["valid_to"],
                    "title": title,
                }
            )

        self._refresh()

    def _on_disable(self):
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return

        r = self._rules_local[idx]
        if r.get("op") == "deactivate" or not r.get("is_active", True):
            return

        if r.get("id"):
            try:
                set_rule_active(
                    user_id=self._user_id,
                    role_code=self._role_code,
                    rule_id=int(r["id"]),
                    is_active=False,
                )
            except Exception as e:
                QMessageBox.critical(self, "Правила", f"Не удалось отключить правило:\n{e}")
                return

            ans = QMessageBox.question(
                self,
                "Правило отключено",
                "Правило отключено. Уже созданные бронирования останутся.\n\n"
                "Отменить будущие бронирования автоматически?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if ans == QMessageBox.StandardButton.Yes:
                try:
                    cancelled = cancel_future_gz_bookings_like_rule(
                        venue_unit_id=int(r["venue_unit_id"]),
                        weekday=int(r["weekday"]),
                        starts_at=r["starts_at"],
                        ends_at=r["ends_at"],
                        from_day=date.today(),
                        title=(r.get("title") or "").strip(),
                    )
                    QMessageBox.information(self, "Бронирования", f"Отменено бронирований: {cancelled}")
                except Exception as e:
                    QMessageBox.warning(self, "Бронирования", f"Не удалось отменить бронирования:\n{e}")

        r["op"] = "deactivate"
        r["is_active"] = False
        self._refresh()

    def _on_delete(self):
        if not self._is_admin:
            QMessageBox.warning(self, "Правила", "Недостаточно прав.")
            return

        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return

        r = self._rules_local[idx]

        if not r.get("id"):
            self._rules_local.pop(idx)
            self._refresh()
            return

        if (
            QMessageBox.question(
                self,
                "Удалить правило",
                "Удалить правило полностью?\n\n"
                "Будущие бронирования, похожие на это правило, будут отменены.\n"
                "Действие необратимо.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            cancel_future_gz_bookings_like_rule(
                venue_unit_id=int(r["venue_unit_id"]),
                weekday=int(r["weekday"]),
                starts_at=r["starts_at"],
                ends_at=r["ends_at"],
                from_day=date.today(),
                title=(r.get("title") or "").strip(),
            )
            delete_rule(
                user_id=self._user_id,
                role_code=self._role_code,
                rule_id=int(r["id"]),
            )
        except Exception as e:
            QMessageBox.critical(self, "Удалить правило", f"Ошибка:\n{e}")
            return

        self._rules_local.pop(idx)
        self._refresh()
