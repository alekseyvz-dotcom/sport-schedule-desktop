from __future__ import annotations

from datetime import date
from typing import Optional, Dict, List

from PySide6.QtCore import Qt, QTimer
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
from app.services.tenant_rules_service import (
    list_rules_for_tenant,
    set_rule_active,
    delete_rule,
)
from app.services.bookings_service import cancel_future_bookings_like_rule
from app.ui.tenant_rule_dialog import TenantRuleDialog


def _weekday_name(w: int) -> str:
    return ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][int(w)]


class TenantRulesWidget(QWidget):
    """
    Готовый виджет правил (tenant_recurring_rules) для встраивания в TenantDialog.

    Особенности:
    - self._rules_local хранит локальные изменения (нужно для создания нового контрагента).
    - если tenant_id задан: читает/пишет в БД (disable/delete реально меняют БД).
    - add/edit работают через TenantRuleDialog (с проверкой доступности).
    """

    COLS = ["День", "Время", "Зона", "Период", "Комментарий", "Активно"]

    def __init__(
        self,
        parent=None,
        *,
        tenant_id: Optional[int],
        contract_from: Optional[date],
        contract_to: Optional[date],
        tenant_kind: str = "legal",  # 'legal'|'person'
        is_admin: bool = False,
        user_id: int,
        role_code: str,
        tz_name: str = "Europe/Moscow",
    ):
        super().__init__(parent)
        self._tenant_id = tenant_id
        self._contract_from = contract_from
        self._contract_to = contract_to
        self._tenant_kind = (tenant_kind or "legal").strip()
        self._is_admin = bool(is_admin)
        self._user_id = int(user_id)
        self._role_code = str(role_code or "")
        self._tz_name = tz_name
        self.btn_add.setObjectName("primary")

        # [{"id": unit_id, "venue_id": venue_id, "sort_order": int, "label": "..."}]
        self._units: List[Dict] = []
        # [{"id","weekday","venue_unit_id","starts_at","ends_at","valid_from","valid_to","title","is_active","op"}]
        self._rules_local: List[Dict] = []

        # ---- UI
        self.tbl = QTableWidget(0, len(self.COLS))
        self.tbl.setHorizontalHeaderLabels(self.COLS)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setAlternatingRowColors(True)

        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Изменить")
        self.btn_disable = QPushButton("Отключить")
        self.btn_delete = QPushButton("Удалить")
        self.btn_delete.setVisible(self._is_admin)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_disable.clicked.connect(self._on_disable)
        self.btn_delete.clicked.connect(self._on_delete)

        top = QHBoxLayout()
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_disable)
        if self._is_admin:
            top.addWidget(self.btn_delete)
        top.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.tbl)

        QTimer.singleShot(0, self.reload)

    # ---------- Public API ----------
    def reload(self) -> None:
        """Перезагрузка правил и справочников зон."""
        try:
            self._units = self._load_units_flat()
            if self._tenant_id:
                self._load_from_db()
            else:
                self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "Правила", f"Ошибка загрузки:\n{type(e).__name__}: {e}")
            self._refresh()

    def set_tenant_id(self, tenant_id: Optional[int]) -> None:
        """После создания контрагента можно установить tenant_id и перечитать правила из БД."""
        self._tenant_id = tenant_id
        self.reload()

    def set_contract_period(self, contract_from: Optional[date], contract_to: Optional[date]) -> None:
        self._contract_from = contract_from
        self._contract_to = contract_to

    def set_tenant_kind(self, tenant_kind: str) -> None:
        self._tenant_kind = (tenant_kind or "legal").strip()

    def rules_payload(self) -> List[Dict]:
        """
        Payload для TenantDialog: список правил с op (keep/new/deactivate/delete).
        Для существующего tenant_id обычно не нужен, но оставляем совместимость.
        """
        return list(self._rules_local)

    # ---------- Internals ----------
    def _default_rule_title(self) -> str:
        return "Оферта" if self._tenant_kind == "person" else "Аренда по договору"

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
                            "sort_order": int(getattr(u, "sort_order", 0)),
                            "label": f"{org.name} / {v.name} — {u.name}",
                        }
                    )
        return out

    def _load_from_db(self) -> None:
        rules = list_rules_for_tenant(
            user_id=self._user_id,
            role_code=self._role_code,
            tenant_id=int(self._tenant_id),
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

    def _selected_index(self) -> Optional[int]:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        if not it:
            return None
        return int(it.data(Qt.ItemDataRole.UserRole))

    def _unit_label(self, unit_id: int) -> str:
        return next((u["label"] for u in self._units if int(u["id"]) == int(unit_id)), f"unit_id={unit_id}")

    def _refresh(self) -> None:
        self.tbl.setRowCount(0)

        for idx, r in enumerate(self._rules_local):
            self.tbl.insertRow(idx)

            it_day = QTableWidgetItem(_weekday_name(r["weekday"]))
            it_day.setData(Qt.ItemDataRole.UserRole, idx)

            it_time = QTableWidgetItem(f"{r['starts_at']:%H:%M}–{r['ends_at']:%H:%M}")
            it_zone = QTableWidgetItem(self._unit_label(int(r["venue_unit_id"])))
            it_period = QTableWidgetItem(f"{r['valid_from']:%d.%m.%Y}–{r['valid_to']:%d.%m.%Y}")
            it_title = QTableWidgetItem(r.get("title", "") or "")

            is_active = bool(r.get("is_active", True)) and r.get("op") != "deactivate"
            it_active = QTableWidgetItem("Да" if is_active else "Нет")

            self.tbl.setItem(idx, 0, it_day)
            self.tbl.setItem(idx, 1, it_time)
            self.tbl.setItem(idx, 2, it_zone)
            self.tbl.setItem(idx, 3, it_period)
            self.tbl.setItem(idx, 4, it_title)
            self.tbl.setItem(idx, 5, it_active)

            if r.get("op") == "deactivate" or not r.get("is_active", True):
                for c in range(self.tbl.columnCount()):
                    item = self.tbl.item(idx, c)
                    if item:
                        item.setForeground(Qt.GlobalColor.gray)

        self.tbl.resizeColumnsToContents()

    # ---------- Actions ----------
    def _on_add(self) -> None:
        dlg = TenantRuleDialog(
            self,
            venue_units=self._units,
            contract_valid_from=self._contract_from,
            contract_valid_to=self._contract_to,
            tz_name=self._tz_name,
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
                    "weekday": int(v["weekday"]),
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

    def _on_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return

        r = self._rules_local[idx]
        if r.get("op") == "deactivate" or not r.get("is_active", True):
            QMessageBox.information(self, "Правила", "Правило отключено и не редактируется.")
            return

        dlg = TenantRuleDialog(
            self,
            title="Изменить правило",
            venue_units=self._units,
            initial=r,
            contract_valid_from=self._contract_from,
            contract_valid_to=self._contract_to,
            tz_name=self._tz_name,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        v = dlg.values()
        title = (v.get("title") or "").strip() or self._default_rule_title()

        # Если правило уже в БД — старая запись отключается, новая создаётся (без update_rule)
        if r.get("id"):
            r["op"] = "deactivate"
            r["is_active"] = False

            # В edit оставляем только первую выбранную зону (venue_unit_id),
            # потому что старое правило было про одну зону.
            self._rules_local.append(
                {
                    "id": None,
                    "weekday": int(v["weekday"]),
                    "venue_unit_id": int(v["venue_unit_id"]),
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
                    "weekday": int(v["weekday"]),
                    "venue_unit_id": int(v["venue_unit_id"]),
                    "starts_at": v["starts_at"],
                    "ends_at": v["ends_at"],
                    "valid_from": v["valid_from"],
                    "valid_to": v["valid_to"],
                    "title": title,
                }
            )

        self._refresh()

    def _on_disable(self) -> None:
        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return

        r = self._rules_local[idx]
        if r.get("op") == "deactivate" or not r.get("is_active", True):
            return

        # Если правила ещё не в БД (создание контрагента) — просто помечаем локально
        if not self._tenant_id or not r.get("id"):
            r["op"] = "deactivate"
            r["is_active"] = False
            self._refresh()
            return

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
                cancelled = cancel_future_bookings_like_rule(
                    tenant_id=int(self._tenant_id),
                    venue_unit_id=int(r["venue_unit_id"]),
                    weekday=int(r["weekday"]),
                    starts_at=r["starts_at"],
                    ends_at=r["ends_at"],
                    from_day=date.today(),
                    activity="PD",
                )
                QMessageBox.information(self, "Бронирования", f"Отменено бронирований: {cancelled}")
            except Exception as e:
                QMessageBox.warning(self, "Бронирования", f"Не удалось отменить бронирования:\n{e}")

        r["op"] = "deactivate"
        r["is_active"] = False
        self._refresh()

    def _on_delete(self) -> None:
        if not self._is_admin:
            QMessageBox.warning(self, "Правила", "Недостаточно прав.")
            return

        idx = self._selected_index()
        if idx is None:
            QMessageBox.information(self, "Правила", "Выберите правило.")
            return

        r = self._rules_local[idx]

        # локальное (ещё не в БД) — просто убрать
        if not r.get("id"):
            self._rules_local.pop(idx)
            self._refresh()
            return

        if not self._tenant_id:
            QMessageBox.warning(self, "Правила", "Нельзя удалить правило: контрагент ещё не сохранён.")
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
            cancel_future_bookings_like_rule(
                tenant_id=int(self._tenant_id),
                venue_unit_id=int(r["venue_unit_id"]),
                weekday=int(r["weekday"]),
                starts_at=r["starts_at"],
                ends_at=r["ends_at"],
                from_day=date.today(),
                activity="PD",
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
