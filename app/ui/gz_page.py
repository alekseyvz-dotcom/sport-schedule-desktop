# app/ui/gz_page.py
from __future__ import annotations

from datetime import timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QCheckBox,
    QHeaderView,
    QAbstractItemView,
    QDialog,
)

from app.services.users_service import AuthUser
from app.services.gz_service import (
    GzGroup,
    list_groups,
    list_coaches,
    create_group,
    update_group,
    set_group_active,
    list_accessible_org_ids,
)
from app.services.gz_rules_service import (
    create_rule,
    set_rule_active,
    generate_bookings_for_group,
)
from app.ui.gz_group_dialog import GzGroupDialog
from app.ui.gz_coaches_window import GzCoachesWindow


class GzPage(QWidget):
    TZ = timezone(timedelta(hours=3))

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._user = user
        self._role = (getattr(user, "role_code", "") or "").lower()
        self._is_admin = self._role == "admin"
        self._can_edit = (self._role == "admin") or bool(
            list_accessible_org_ids(user_id=int(self._user.id), for_edit=True)
        )

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск: тренер / группа")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_coaches = QPushButton("Тренеры…")
        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")

        self.btn_coaches.clicked.connect(self._on_coaches)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)

        top = QHBoxLayout()
        top.setContentsMargins(12, 12, 12, 8)
        top.setSpacing(10)
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_coaches)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["ID", "Тренер", "Группа", "Примечание", "Активен"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setShowGrid(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(lambda *_: self._on_edit())

        header = self.tbl.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        self._apply_ui_access()
        self.reload()

    def _apply_ui_access(self):
        self.btn_add.setEnabled(self._can_edit)
        self.btn_edit.setEnabled(self._can_edit)
        self.btn_archive.setEnabled(self._can_edit)
        self.btn_coaches.setEnabled(self._can_edit)

    def _on_coaches(self):
        if not self._can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование тренеров.")
            return
        dlg = GzCoachesWindow(self._user, self)
        dlg.exec()
        self.reload()

    def _selected_group(self) -> GzGroup | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    def reload(self):
        try:
            groups = list_groups(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
                user_id=self._user.id,
                role_code=self._user.role_code,
            )
        except Exception as e:
            QMessageBox.critical(self, "Гос. задание", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for g in groups:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(g.id))
            it_id.setData(Qt.UserRole, g)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_active = QTableWidgetItem("Да" if g.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, QTableWidgetItem(g.coach_name))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(g.group_year)))
            self.tbl.setItem(r, 3, QTableWidgetItem(g.notes or ""))
            self.tbl.setItem(r, 4, it_active)

            if not g.is_active:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

    def _apply_rules_and_maybe_generate(self, gz_group_id: int, rules_payload: list[dict]) -> None:
        if not self._can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на изменение правил/генерацию бронирований.")
            return

        try:
            for r in rules_payload:
                op = r.get("op", "keep")
                if op == "new":
                    create_rule(
                        user_id=self._user.id,
                        role_code=self._user.role_code,
                        gz_group_id=int(gz_group_id),
                        venue_unit_id=int(r["venue_unit_id"]),
                        weekday=int(r["weekday"]),
                        starts_at=r["starts_at"],
                        ends_at=r["ends_at"],
                        valid_from=r["valid_from"],
                        valid_to=r["valid_to"],
                        title=r.get("title", "") or "",
                    )
                elif op == "deactivate" and r.get("id"):
                    set_rule_active(
                        user_id=self._user.id,
                        role_code=self._user.role_code,
                        rule_id=int(r["id"]),
                        is_active=False,
                    )
        except Exception as e:
            QMessageBox.critical(self, "Правила ГЗ", f"Ошибка сохранения правил:\n{e}")
            return

        has_new = any(r.get("op") == "new" for r in rules_payload)
        if not has_new:
            return

        if (
            QMessageBox.question(
                self,
                "Генерация бронирований",
                "Создать бронирования ГЗ по новым правилам до конца периода действия правила?\n\n"
                "Если какие-то даты уже заняты — они будут пропущены.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            rep = generate_bookings_for_group(
                user_id=self._user.id,
                role_code=self._user.role_code,
                gz_group_id=int(gz_group_id),
                tz=self.TZ,
            )
        except Exception as e:
            QMessageBox.critical(self, "Генерация бронирований", f"Ошибка генерации:\n{e}")
            return

        msg = (
            f"Создано бронирований: {rep.created}\n"
            f"Занято/уже существует: {rep.skipped_busy}\n"
            f"Ошибок: {rep.skipped_error}"
        )
        if rep.errors:
            msg += "\n\nПервые ошибки:\n" + "\n".join(rep.errors[:8])
            if len(rep.errors) > 8:
                msg += f"\n... и ещё {len(rep.errors) - 8}"
        QMessageBox.information(self, "Генерация бронирований", msg)

    def _on_add(self):
        if not self._can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на создание групп ГЗ.")
            return

        try:
            coaches = list_coaches(
                include_inactive=False,
                user_id=self._user.id,
                role_code=self._user.role_code,
            )
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Ошибка загрузки тренеров:\n{e}")
            return

        if not coaches:
            QMessageBox.information(self, "Гос. задание", "Нет доступных тренеров для ваших учреждений.")
            return

        dlg = GzGroupDialog(self, title="Создать группу ГЗ", coaches=coaches, is_admin=self._is_admin, user_id=int(self._user.id), role_code=str(self._user.role_code))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        rules_payload = dlg.rules_payload() if hasattr(dlg, "rules_payload") else []

        try:
            new_id = create_group(
                user_id=self._user.id,
                role_code=self._user.role_code,
                coach_id=data["coach_id"],
                group_year=data["group_year"],
                notes=data.get("notes", ""),
                is_free=bool(data.get("is_free", False)),
                period_from=data.get("period_from"),
                period_to=data.get("period_to"),
            )
        except Exception as e:
            QMessageBox.critical(self, "Создать группу ГЗ", f"Ошибка:\n{e}")
            return

        if rules_payload:
            self._apply_rules_and_maybe_generate(new_id, rules_payload)

        self.reload()
        self._select_row_by_id(new_id)

    def _on_edit(self):
        if not self._can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на редактирование групп ГЗ.")
            return

        g = self._selected_group()
        if not g:
            QMessageBox.information(self, "Редактировать", "Выберите группу.")
            return

        try:
            coaches = list_coaches(
                include_inactive=False,
                user_id=self._user.id,
                role_code=self._user.role_code,
            )
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Ошибка загрузки тренеров:\n{e}")
            return

        dlg = GzGroupDialog(
            self,
            title=f"Редактировать: {g.coach_name} — {g.group_year}",
            coaches=coaches,
            is_admin=self._is_admin,
            user_id=int(self._user.id),
            role_code=str(self._user.role_code),
            data={
                "id": g.id,
                "coach_id": g.coach_id,
                "group_year": g.group_year,
                "notes": g.notes,
                "is_free": getattr(g, "is_free", False),
                "period_from": getattr(g, "period_from", None),
                "period_to": getattr(g, "period_to", None),
            },
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        rules_payload = dlg.rules_payload() if hasattr(dlg, "rules_payload") else []

        try:
            update_group(
                user_id=self._user.id,
                role_code=self._user.role_code,
                group_id=g.id,
                coach_id=data["coach_id"],
                group_year=data["group_year"],
                notes=data.get("notes", ""),
                is_free=bool(data.get("is_free", False)),
                period_from=data.get("period_from"),
                period_to=data.get("period_to"),
            )
        except Exception as e:
            QMessageBox.critical(self, "Редактировать группу ГЗ", f"Ошибка:\n{e}")
            return

        if rules_payload:
            self._apply_rules_and_maybe_generate(g.id, rules_payload)

        self.reload()
        self._select_row_by_id(g.id)

    def _on_toggle_active(self):
        if not self._can_edit:
            QMessageBox.warning(self, "Доступ запрещён", "У вас нет прав на изменение статуса групп ГЗ.")
            return

        g = self._selected_group()
        if not g:
            QMessageBox.information(self, "Архив", "Выберите группу.")
            return

        new_state = not g.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы действительно хотите {action} группу «{g.coach_name} — {g.group_year}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_group_active(
                user_id=self._user.id,
                role_code=self._user.role_code,
                group_id=g.id,
                is_active=new_state,
            )
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload()
        self._select_row_by_id(g.id)

    def _select_row_by_id(self, group_id: int) -> None:
        for r in range(self.tbl.rowCount()):
            it = self.tbl.item(r, 0)
            if it and it.text() == str(group_id):
                self.tbl.setCurrentCell(r, 0)
                self.tbl.scrollToItem(it)
                return
