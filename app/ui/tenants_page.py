from __future__ import annotations

from datetime import timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
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
    QDialog,
    QHeaderView,
    QAbstractItemView,
    QStyle,
)

from app.services.users_service import AuthUser
from app.services.tenants_service import (
    Tenant,
    list_tenants,
    create_tenant,
    update_tenant,
    set_tenant_active,
)
from app.services.tenant_rules_service import (
    create_rule,
    set_rule_active,
    generate_bookings_for_tenant,
)
from app.ui.tenant_dialog import TenantDialog


class TenantsPage(QWidget):
    TZ = timezone(timedelta(hours=3))

    # Минимальная ширина колонки "ФИО / Название" (чтобы всегда было читаемо)
    NAME_MIN_WIDTH = 260

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self._user = user
        self._is_admin = (getattr(user, "role_code", "") == "admin")

        # --- Top bar ---
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск: имя / ИНН / телефон")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)

        for b in (self.btn_add, self.btn_edit, self.btn_archive):
            b.setMinimumHeight(34)

        top = QHBoxLayout()
        top.setContentsMargins(12, 12, 12, 8)
        top.setSpacing(10)
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        # --- Table ---
        self.tbl = QTableWidget(0, 14)
        self.tbl.setHorizontalHeaderLabels(
            [
                "ID",
                "ФИО / Название",
                "Тип",
                "Аренда",
                "ИНН",
                "Телефон",
                "Email",
                "Контакт",
                "№ договора",
                "Срок с",
                "Срок по",
                "Статус",
                "Активен",
                "Комментарий",
            ]
        )

        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSortingEnabled(True)
        self.tbl.setShowGrid(False)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(self._on_edit)

        # Горизонтальный скролл появится, если места мало (важно для "ФИО всегда читаемо")
        self.tbl.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header = self.tbl.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        
        # 1) Пользователь может двигать
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # 2) Последняя колонка (Комментарий) тянется и "съедает" остаток
        header.setStretchLastSection(True)
        
        # Узкие колонки по содержимому
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)   # ID
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)   # Тип
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)   # Аренда
        header.setSectionResizeMode(12, QHeaderView.ResizeMode.ResizeToContents)  # Активен
        
        # ВАЖНО: ФИО делаем НЕ Stretch, а Interactive (чтобы ширина не схлопывалась)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(13, QHeaderView.ResizeMode.Interactive)
        
        # Стартовые ширины
        header.setMinimumSectionSize(80)
        self.tbl.setColumnWidth(1, 420)   # ФИО/Название (сразу широко)
        self.tbl.setColumnWidth(13, 260)  # Комментарий (можно, но он всё равно будет тянуться)
        
        # Остальным задаем разумные стартовые ширины
        self.tbl.setColumnWidth(4, 90)    # ИНН
        self.tbl.setColumnWidth(5, 120)   # Телефон
        self.tbl.setColumnWidth(6, 180)   # Email
        self.tbl.setColumnWidth(7, 150)   # Контакт
        self.tbl.setColumnWidth(8, 120)   # № договора
        self.tbl.setColumnWidth(9, 95)    # Срок с
        self.tbl.setColumnWidth(10, 95)   # Срок по
        self.tbl.setColumnWidth(11, 120)  # Статус


        self.tbl.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                gridline-color: transparent;
                selection-background-color: #d6e9ff;
                selection-color: #111111;
            }
            QHeaderView::section {
                background: #f6f7f9;
                color: #111111;
                padding: 8px 10px;
                border: none;
                border-bottom: 1px solid #e6e6e6;
                font-weight: 600;
            }
            QTableWidget::item {
                padding: 6px 10px;
                border: none;
            }
            QTableWidget::item:selected {
                background: #d6e9ff;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)

        self.setStyleSheet(
            """
            QWidget { background: #fbfbfc; }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QLineEdit:focus { border: 1px solid #7fb3ff; }
            QPushButton {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover { border: 1px solid #cfd6df; background: #f6f7f9; }
            QPushButton:pressed { background: #eef1f5; }
            QCheckBox { padding: 0 6px; }
            """
        )

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        self.tbl.setFont(f)

        # Иконки (используем стандартные значки Qt, чтобы не тянуть файлы)
        style = self.style()
        self._ico_person = style.standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon)     # можно заменить
        self._ico_legal = style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)    # можно заменить
        self._ico_one_time = style.standardIcon(QStyle.StandardPixmap.SP_BrowserStop) # можно заменить
        self._ico_long = style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)   # можно заменить

        self.reload()

    def _selected_tenant(self) -> Tenant | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        item = self.tbl.item(row, 0)
        if not item:
            return None
        t = item.data(Qt.UserRole)
        return t if isinstance(t, Tenant) else None

    @staticmethod
    def _kind_text(kind: str) -> str:
        return "ФЛ" if (kind or "") == "person" else "ЮЛ"

    @staticmethod
    def _rent_text(rent: str) -> str:
        return "Разово" if (rent or "") == "one_time" else "Долгосрочно"

    def reload(self):
        try:
            tenants = list_tenants(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Контрагенты", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(0)

        for t in tenants:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            it_id = QTableWidgetItem(str(t.id))
            it_id.setData(Qt.UserRole, t)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_active = QTableWidgetItem("Да" if t.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            tenant_kind = getattr(t, "tenant_kind", "legal") or "legal"
            rent_kind = getattr(t, "rent_kind", "long_term") or "long_term"

            it_kind = QTableWidgetItem(self._kind_text(tenant_kind))
            it_kind.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_kind.setIcon(self._ico_person if tenant_kind == "person" else self._ico_legal)

            it_rent = QTableWidgetItem(self._rent_text(rent_kind))
            it_rent.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_rent.setIcon(self._ico_one_time if rent_kind == "one_time" else self._ico_long)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, QTableWidgetItem(t.name))
            self.tbl.setItem(r, 2, it_kind)
            self.tbl.setItem(r, 3, it_rent)

            self.tbl.setItem(r, 4, QTableWidgetItem(t.inn or ""))
            self.tbl.setItem(r, 5, QTableWidgetItem(t.phone or ""))
            self.tbl.setItem(r, 6, QTableWidgetItem(t.email or ""))
            self.tbl.setItem(r, 7, QTableWidgetItem(t.contact_name or ""))
            self.tbl.setItem(r, 8, QTableWidgetItem(t.contract_no or ""))
            self.tbl.setItem(
                r, 9, QTableWidgetItem(f"{t.contract_valid_from:%d.%m.%Y}" if t.contract_valid_from else "")
            )
            self.tbl.setItem(
                r, 10, QTableWidgetItem(f"{t.contract_valid_to:%d.%m.%Y}" if t.contract_valid_to else "")
            )
            self.tbl.setItem(r, 11, QTableWidgetItem(t.status or ""))
            self.tbl.setItem(r, 12, it_active)
            self.tbl.setItem(r, 13, QTableWidgetItem(t.comment or ""))

            if not t.is_active:
                for c in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, c)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

        self.tbl.setSortingEnabled(True)

        # На всякий случай: после перезагрузки еще раз удерживаем минимум ширины ФИО
        self.tbl.horizontalHeader().setStretchLastSection(True)
        if self.tbl.columnWidth(1) < self.NAME_MIN_WIDTH:
            self.tbl.setColumnWidth(1, self.NAME_MIN_WIDTH)

    def _apply_rules_and_maybe_generate(self, tenant_id: int, rules_payload: list[dict]) -> None:
        try:
            for r in rules_payload:
                op = r.get("op", "keep")
                if op == "new":
                    create_rule(
                        tenant_id=int(tenant_id),
                        venue_unit_id=int(r["venue_unit_id"]),
                        weekday=int(r["weekday"]),
                        starts_at=r["starts_at"],
                        ends_at=r["ends_at"],
                        valid_from=r["valid_from"],
                        valid_to=r["valid_to"],
                        title=r.get("title", "") or "",
                    )
                elif op == "deactivate" and r.get("id"):
                    set_rule_active(int(r["id"]), False)
        except Exception as e:
            QMessageBox.critical(self, "Правила расписания", f"Ошибка сохранения правил:\n{e}")
            return

        has_new = any(r.get("op") == "new" for r in rules_payload)
        if not has_new:
            return

        if (
            QMessageBox.question(
                self,
                "Генерация бронирований",
                "Создать бронирования по новым правилам до конца периода действия правила?\n\n"
                "Если какие-то даты уже заняты — они будут пропущены.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            rep = generate_bookings_for_tenant(tenant_id=int(tenant_id), tz=self.TZ)
        except Exception as e:
            QMessageBox.critical(self, "Генерация бронирований", f"Ошибка генерации:\n{e}")
            return

        msg = f"Создано бронирований: {rep.created}\nПропущено (занято/ошибка): {rep.skipped}"
        if rep.errors:
            msg += "\n\nПервые ошибки:\n" + "\n".join(rep.errors[:8])
            if len(rep.errors) > 8:
                msg += f"\n... и ещё {len(rep.errors) - 8}"
        QMessageBox.information(self, "Генерация бронирований", msg)

    def _on_add(self):
        dlg = TenantDialog(self, title="Создать контрагента", is_admin=self._is_admin)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        rules_payload = dlg.rules_payload() if hasattr(dlg, "rules_payload") else []

        try:
            new_id = create_tenant(**data)
        except Exception as e:
            QMessageBox.critical(self, "Создать контрагента", f"Ошибка:\n{e}")
            return

        if rules_payload:
            self._apply_rules_and_maybe_generate(new_id, rules_payload)

        QMessageBox.information(self, "Контрагенты", f"Создан контрагент (id={new_id}).")
        self.reload()
        self._select_row_by_id(new_id)

    def _on_edit(self):
        t = self._selected_tenant()
        if not t:
            QMessageBox.information(self, "Редактировать", "Выберите контрагента в списке.")
            return

        dlg = TenantDialog(
            self,
            title=f"Редактировать: {t.name}",
            is_admin=self._is_admin,
            data={
                "id": t.id,
                "name": t.name,
                "inn": t.inn,
                "phone": t.phone,
                "email": t.email,
                "comment": t.comment,
                "contact_name": t.contact_name,
                "obligation_kind": t.obligation_kind,
                "contract_no": t.contract_no,
                "contract_date": t.contract_date,
                "contract_valid_from": t.contract_valid_from,
                "contract_valid_to": t.contract_valid_to,
                "docs_delivery_method": t.docs_delivery_method,
                "status": t.status,
                "contract_signed": t.contract_signed,
                "attached_in_1c": t.attached_in_1c,
                "has_ds": t.has_ds,
                "notes": t.notes,
                "tenant_kind": getattr(t, "tenant_kind", "legal"),
                "rent_kind": getattr(t, "rent_kind", "long_term"),
            },
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        rules_payload = dlg.rules_payload() if hasattr(dlg, "rules_payload") else []

        try:
            update_tenant(t.id, **data)
        except Exception as e:
            QMessageBox.critical(self, "Редактировать контрагента", f"Ошибка:\n{e}")
            return

        if rules_payload:
            self._apply_rules_and_maybe_generate(t.id, rules_payload)

        self.reload()
        self._select_row_by_id(t.id)

    def _on_toggle_active(self):
        t = self._selected_tenant()
        if not t:
            QMessageBox.information(self, "Архив", "Выберите контрагента в списке.")
            return

        new_state = not t.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self,
                "Подтверждение",
                f"Вы действительно хотите {action} контрагента «{t.name}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_tenant_active(t.id, new_state)
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload()
        self._select_row_by_id(t.id)

    def _select_row_by_id(self, tenant_id: int) -> None:
        for r in range(self.tbl.rowCount()):
            item = self.tbl.item(r, 0)
            if item and item.text() == str(tenant_id):
                self.tbl.setCurrentCell(r, 0)
                self.tbl.scrollToItem(item)
                return
