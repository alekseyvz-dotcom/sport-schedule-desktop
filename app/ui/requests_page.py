from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QLabel,
    QHeaderView, QAbstractItemView, QSizePolicy, QDateEdit,
    QDialog, QTextEdit, QDialogButtonBox,
)

from app.services.users_service import AuthUser
from app.services.access_service import get_org_access
from app.services.orgs_service import list_orgs, SportOrg

from app.ui.badge_delegate import BadgeDelegate, BADGE_BG_ROLE
from app.services.requests_service import list_requests, set_request_status, BookingRequest


_COLOR_NEW = QColor("#4ECDC4")
_COLOR_CONFIRMED = QColor("#6BCB77")
_COLOR_REJECTED = QColor("#FF6B6B")
_COLOR_CANCELLED = QColor("#AAAAAA")
_COLOR_GROUP = QColor("#F0F0FF")  # подсветка строк из одной группы


def _badge(text: str, bg: QColor | None) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if bg is not None:
        it.setData(BADGE_BG_ROLE, bg)
    return it


class _CommentDialog(QDialog):
    def __init__(self, parent=None, title: str = "Комментарий", placeholder: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)

        self.ed = QTextEdit(self)
        self.ed.setPlaceholderText(placeholder)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.addWidget(self.ed, 1)
        lay.addWidget(bb)

    def text(self) -> str:
        return self.ed.toPlainText().strip()


class RequestsPage(QWidget):
    # Индексы колонок
    COL_ID = 0
    COL_STATUS = 1
    COL_DATE = 2
    COL_TIME = 3
    COL_ORG = 4
    COL_VENUE = 5
    COL_PORTION = 6
    COL_ZONE = 7
    COL_CLIENT = 8
    COL_PHONE = 9
    COL_MSG = 10
    COL_STAFF = 11
    NUM_COLS = 12

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.user = user

        self.lbl_title = QLabel("Заявки")
        self.lbl_title.setObjectName("sectionTitle")

        self.cb_org = QComboBox()
        self.cb_org.setMinimumWidth(260)
        self.cb_org.currentIndexChanged.connect(lambda *_: self.reload())

        self.cb_status = QComboBox()
        self.cb_status.addItem("Все статусы", None)
        self.cb_status.addItem("🆕 Новые", "new")
        self.cb_status.addItem("✅ Подтверждённые", "confirmed")
        self.cb_status.addItem("❌ Отклонённые", "rejected")
        self.cb_status.addItem("🚫 Отменённые", "cancelled")
        self.cb_status.currentIndexChanged.connect(lambda *_: self.reload())

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск: ФИО / телефон / email / площадка / зона")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.dt_from = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("dd.MM.yyyy")
        self.dt_from.setDate(dt.date.today() - dt.timedelta(days=7))
        self.dt_from.dateChanged.connect(lambda *_: self.reload())

        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("dd.MM.yyyy")
        self.dt_to.setDate(dt.date.today() + dt.timedelta(days=14))
        self.dt_to.dateChanged.connect(lambda *_: self.reload())

        self.btn_reload = QPushButton("🔄 Обновить")
        self.btn_reload.clicked.connect(self.reload)

        self.btn_confirm = QPushButton("✅ Подтвердить")
        self.btn_reject = QPushButton("❌ Отклонить…")
        self.btn_cancel = QPushButton("🚫 Отменить")
        for b in (self.btn_confirm, self.btn_reject, self.btn_cancel):
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_confirm.clicked.connect(self._confirm)
        self.btn_reject.clicked.connect(self._reject)
        self.btn_cancel.clicked.connect(self._cancel)

        self.tbl = QTableWidget(0, self.NUM_COLS)
        self.tbl.setObjectName("requestsTable")
        self.tbl.setHorizontalHeaderLabels([
            "ID",
            "Статус",
            "Дата",
            "Время",
            "Учреждение",
            "Площадка",
            "Часть",
            "Зоны",
            "Клиент",
            "Телефон",
            "Комментарий клиента",
            "Комментарий сотрудника",
        ])
        self._style_table(self.tbl)
        self.tbl.itemSelectionChanged.connect(self._apply_ui_access)
        self.tbl.doubleClicked.connect(self._open_details)

        self._delegate = BadgeDelegate(self.tbl)
        self.tbl.setItemDelegate(self._delegate)

        row_filters = QHBoxLayout()
        row_filters.setContentsMargins(0, 0, 0, 0)
        row_filters.setSpacing(8)
        row_filters.addWidget(self.lbl_title)
        row_filters.addSpacing(6)
        row_filters.addWidget(QLabel("Учреждение:"))
        row_filters.addWidget(self.cb_org)
        row_filters.addWidget(QLabel("Статус:"))
        row_filters.addWidget(self.cb_status)
        row_filters.addWidget(QLabel("С:"))
        row_filters.addWidget(self.dt_from)
        row_filters.addWidget(QLabel("По:"))
        row_filters.addWidget(self.dt_to)
        row_filters.addWidget(self.ed_search, 1)
        row_filters.addWidget(self.btn_reload)

        row_actions = QHBoxLayout()
        row_actions.setContentsMargins(0, 0, 0, 0)
        row_actions.setSpacing(6)
        row_actions.addWidget(self.btn_confirm)
        row_actions.addWidget(self.btn_reject)
        row_actions.addWidget(self.btn_cancel)
        row_actions.addStretch(1)

        card = QWidget(self)
        card.setObjectName("detailsCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        card_lay.setSpacing(6)
        card_lay.addLayout(row_actions)
        card_lay.addWidget(self.tbl, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)
        root.addLayout(row_filters)
        root.addWidget(card, 1)

        self._load_orgs()
        self.reload()

    def _is_admin(self) -> bool:
        return (self.user.role_code or "").lower() == "admin"

    def _org_access(self, org_id: int):
        return get_org_access(
            user_id=self.user.id,
            role_code=self.user.role_code,
            org_id=org_id,
        )

    def _style_table(self, tbl: QTableWidget) -> None:
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setAlternatingRowColors(False)
        tbl.setSortingEnabled(True)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)

        header = tbl.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        tbl.setFont(f)

        for c in range(tbl.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(tbl.columnCount() - 1, QHeaderView.ResizeMode.Stretch)

    def _load_orgs(self):
        try:
            orgs = list_orgs(
                user_id=self.user.id,
                role_code=self.user.role_code,
                search="",
                include_inactive=False,
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка загрузки учреждений:\n{e}")
            orgs = []

        self.cb_org.blockSignals(True)
        self.cb_org.clear()
        self.cb_org.addItem("Все учреждения", None)
        for o in orgs:
            self.cb_org.addItem(o.name, o)
        self.cb_org.blockSignals(False)

    def _selected_request(self) -> BookingRequest | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        item = self.tbl.item(row, self.COL_ID)
        if not item:
            return None
        obj = item.data(Qt.ItemDataRole.UserRole)
        return obj if isinstance(obj, BookingRequest) else None

    def _apply_ui_access(self):
        req = self._selected_request()
        if not req:
            for b in (self.btn_confirm, self.btn_reject, self.btn_cancel):
                b.setEnabled(False)
            return

        acc = self._org_access(req.org_id)
        can_edit = bool(getattr(acc, "can_edit", False)) or self._is_admin()

        self.btn_confirm.setEnabled(can_edit and req.status == "new")
        self.btn_reject.setEnabled(can_edit and req.status == "new")
        self.btn_cancel.setEnabled(can_edit and req.status in ("new", "confirmed"))

    def reload(self):
        org_obj = self.cb_org.currentData()
        org_id = org_obj.id if isinstance(org_obj, SportOrg) else None

        status = self.cb_status.currentData()
        search = self.ed_search.text().strip() or None
        date_from = self.dt_from.date().toPython()
        date_to = self.dt_to.date().toPython()

        try:
            reqs = list_requests(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org_id,
                status=status,
                search=search,
                date_from=date_from,
                date_to=date_to,
                limit=2000,
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(0)

        # Отслеживаем показанные group_id чтобы не дублировать групповые
        seen_groups: set[str] = set()

        for r in reqs:
            # Если заявка с group_id и мы уже показали строку для этой группы — пропускаем
            if r.group_id:
                if r.group_id in seen_groups:
                    continue
                seen_groups.add(r.group_id)

            row = self.tbl.rowCount()
            self.tbl.insertRow(row)

            # ID — показываем id первой заявки, для групповых добавляем маркер
            id_text = str(r.id)
            if r.group_id:
                id_text = f"{r.id} 🔗"

            it_id = QTableWidgetItem(id_text)
            it_id.setData(Qt.ItemDataRole.UserRole, r)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            if r.status == "new":
                it_status = _badge("🆕 Новая", _COLOR_NEW)
            elif r.status == "confirmed":
                it_status = _badge("✅ Подтв.", _COLOR_CONFIRMED)
            elif r.status == "rejected":
                it_status = _badge("❌ Откл.", _COLOR_REJECTED)
            else:
                it_status = _badge("🚫 Отм.", _COLOR_CANCELLED)

            it_date = QTableWidgetItem(r.desired_date.strftime("%d.%m.%Y"))
            it_time = QTableWidgetItem(f"{r.desired_start:%H:%M}–{r.desired_end:%H:%M}")

            # Часть площадки
            it_portion = QTableWidgetItem(r.portion_label or "—")
            it_portion.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Зоны
            zone_text = r.group_unit_names or r.unit_name or "—"
            it_zone = QTableWidgetItem(zone_text)

            self.tbl.setItem(row, self.COL_ID, it_id)
            self.tbl.setItem(row, self.COL_STATUS, it_status)
            self.tbl.setItem(row, self.COL_DATE, it_date)
            self.tbl.setItem(row, self.COL_TIME, it_time)
            self.tbl.setItem(row, self.COL_ORG, QTableWidgetItem(r.org_name))
            self.tbl.setItem(row, self.COL_VENUE, QTableWidgetItem(r.venue_name))
            self.tbl.setItem(row, self.COL_PORTION, it_portion)
            self.tbl.setItem(row, self.COL_ZONE, it_zone)
            self.tbl.setItem(row, self.COL_CLIENT, QTableWidgetItem(r.contact_name or ""))
            self.tbl.setItem(row, self.COL_PHONE, QTableWidgetItem(r.contact_phone or ""))
            self.tbl.setItem(row, self.COL_MSG, QTableWidgetItem(r.message or ""))
            self.tbl.setItem(row, self.COL_STAFF, QTableWidgetItem(r.staff_comment or ""))

        self.tbl.setSortingEnabled(True)
        self._apply_ui_access()

    def _confirm(self):
        req = self._selected_request()
        if not req:
            return

        group_note = ""
        if req.group_id:
            group_note = f"\n\n⚠️ Это групповое бронирование ({req.portion_label}).\nБудут подтверждены все связанные зоны."

        if QMessageBox.question(
            self, "Подтверждение",
            f"Подтвердить заявку #{req.id}?{group_note}",
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            count = set_request_status(
                user_id=self.user.id,
                role_code=self.user.role_code,
                request_id=req.id,
                status="confirmed",
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка:\n{e}")
            return

        info = f"Заявка #{req.id} подтверждена."
        if count > 1:
            info += f"\nОбновлено заявок: {count}"
        QMessageBox.information(self, "Подтверждение", info)
        self.reload()

    def _reject(self):
        req = self._selected_request()
        if not req:
            return

        group_note = ""
        if req.group_id:
            group_note = f"\n\n⚠️ Групповое бронирование — будут отклонены все связанные зоны."

        dlg = _CommentDialog(
            self,
            title=f"Отклонить заявку #{req.id}",
            placeholder=f"Причина отклонения (сохранится в staff_comment)…{group_note}",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        comment = dlg.text() or None

        try:
            count = set_request_status(
                user_id=self.user.id,
                role_code=self.user.role_code,
                request_id=req.id,
                status="rejected",
                staff_comment=comment,
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка:\n{e}")
            return

        info = f"Заявка #{req.id} отклонена."
        if count > 1:
            info += f"\nОбновлено заявок: {count}"
        QMessageBox.information(self, "Отклонение", info)
        self.reload()

    def _cancel(self):
        req = self._selected_request()
        if not req:
            return

        group_note = ""
        if req.group_id:
            group_note = f"\n\n⚠️ Групповое бронирование — будут отменены все связанные зоны."

        if QMessageBox.question(
            self, "Отмена",
            f"Отменить заявку #{req.id}?{group_note}",
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            count = set_request_status(
                user_id=self.user.id,
                role_code=self.user.role_code,
                request_id=req.id,
                status="cancelled",
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка:\n{e}")
            return

        info = f"Заявка #{req.id} отменена."
        if count > 1:
            info += f"\nОбновлено заявок: {count}"
        QMessageBox.information(self, "Отмена", info)
        self.reload()

    def _open_details(self):
        req = self._selected_request()
        if not req:
            return

        processed = "—"
        if req.processed_at:
            processed = f"{req.processed_at:%d.%m.%Y %H:%M}"

        portion_line = ""
        if req.portion_label:
            portion_line = f"Часть площадки: {req.portion_label}\n"

        zone_line = ""
        if req.group_unit_names:
            zone_line = f"Зоны: {req.group_unit_names}\n"
        elif req.unit_name:
            zone_line = f"Зона: {req.unit_name}\n"

        group_line = ""
        if req.group_id:
            group_line = f"Групповое бронирование: да (group_id: {req.group_id[:8]}…)\n"

        text = (
            f"Заявка #{req.id}\n\n"
            f"Статус: {req.status}\n"
            f"Учреждение: {req.org_name}\n"
            f"Площадка: {req.venue_name}\n"
            f"{portion_line}"
            f"{zone_line}"
            f"{group_line}"
            f"Дата: {req.desired_date:%d.%m.%Y}\n"
            f"Время: {req.desired_start:%H:%M}–{req.desired_end:%H:%M}\n\n"
            f"Клиент: {req.contact_name}\n"
            f"Телефон: {req.contact_phone or '—'}\n"
            f"Email: {req.contact_email or '—'}\n"
            f"Telegram user_id: {req.telegram_user_id or '—'}\n\n"
            f"Комментарий клиента:\n{req.message or '—'}\n\n"
            f"Комментарий сотрудника:\n{req.staff_comment or '—'}\n\n"
            f"Обработано: {processed}\n"
        )
        QMessageBox.information(self, "Заявка", text)
