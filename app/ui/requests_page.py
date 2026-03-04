# app/ui/requests_page.py
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QCheckBox, QComboBox,
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
        self.setMinimumWidth(420)

        self.ed = QTextEdit(self)
        self.ed.setPlaceholderText(placeholder)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.ed, 1)
        lay.addWidget(bb)

    def text(self) -> str:
        return self.ed.toPlainText().strip()


class RequestsPage(QWidget):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.user = user

        # Заголовок
        self.lbl_title = QLabel("Заявки")
        self.lbl_title.setObjectName("sectionTitle")

        # Фильтры
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
        self.ed_search.setPlaceholderText("Поиск: ФИО / телефон / площадка")
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

        # Действия
        self.btn_confirm = QPushButton("✅ Подтвердить")
        self.btn_reject = QPushButton("❌ Отклонить…")
        self.btn_cancel = QPushButton("🚫 Отменить")
        for b in (self.btn_confirm, self.btn_reject, self.btn_cancel):
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_confirm.clicked.connect(self._confirm)
        self.btn_reject.clicked.connect(self._reject)
        self.btn_cancel.clicked.connect(self._cancel)

        # Таблица
        self.tbl = QTableWidget(0, 10)
        self.tbl.setObjectName("requestsTable")
        self.tbl.setHorizontalHeaderLabels([
            "ID",
            "Статус",
            "Дата",
            "Время",
            "Учреждение",
            "Площадка",
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

        # Верхняя панель
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

    # ───────────────────────── helpers ─────────────────────────

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
        # В идеале: только доступные пользователю орг.
        # Здесь берём list_orgs как в вашей странице учреждений.
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
        item = self.tbl.item(row, 0)
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

        # Право определяется по org_id заявки
        acc = self._org_access(req.org_id)
        can_edit = bool(acc.can_edit) or self._is_admin()

        # Подтверждать/отклонять логично только "new"
        self.btn_confirm.setEnabled(can_edit and req.status == "new")
        self.btn_reject.setEnabled(can_edit and req.status == "new")
        # Отменять можно new/confirmed (по вашему регламенту можно иначе)
        self.btn_cancel.setEnabled(can_edit and req.status in ("new", "confirmed"))

    # ───────────────────────── data ─────────────────────────

    def reload(self):
        org_obj = self.cb_org.currentData()
        org_id = org_obj.id if isinstance(org_obj, SportOrg) else None

        status = self.cb_status.currentData()
        search = self.ed_search.text().strip()

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
                limit=1000,
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(0)

        for r in reqs:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)

            it_id = QTableWidgetItem(str(r.id))
            it_id.setData(Qt.ItemDataRole.UserRole, r)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Статус как бейдж
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

            self.tbl.setItem(row, 0, it_id)
            self.tbl.setItem(row, 1, it_status)
            self.tbl.setItem(row, 2, it_date)
            self.tbl.setItem(row, 3, it_time)
            self.tbl.setItem(row, 4, QTableWidgetItem(r.org_name))
            self.tbl.setItem(row, 5, QTableWidgetItem(r.venue_name))
            self.tbl.setItem(row, 6, QTableWidgetItem(r.contact_name or ""))
            self.tbl.setItem(row, 7, QTableWidgetItem(r.contact_phone or ""))
            self.tbl.setItem(row, 8, QTableWidgetItem(r.message or ""))
            self.tbl.setItem(row, 9, QTableWidgetItem(r.staff_comment or ""))

        self.tbl.setSortingEnabled(True)
        self._apply_ui_access()

    # ───────────────────────── actions ─────────────────────────

    def _confirm(self):
        req = self._selected_request()
        if not req:
            return

        if QMessageBox.question(self, "Подтверждение", f"Подтвердить заявку #{req.id}?") != QMessageBox.StandardButton.Yes:
            return

        try:
            set_request_status(
                user_id=self.user.id,
                role_code=self.user.role_code,
                request_id=req.id,
                status="confirmed",
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка:\n{e}")
            return

        self.reload()

    def _reject(self):
        req = self._selected_request()
        if not req:
            return

        dlg = _CommentDialog(
            self,
            title=f"Отклонить заявку #{req.id}",
            placeholder="Причина отклонения (необязательно, но желательно)…",
        )
        if dlg.exec() != QDialog.Accepted:
            return

        comment = dlg.text() or None

        try:
            set_request_status(
                user_id=self.user.id,
                role_code=self.user.role_code,
                request_id=req.id,
                status="rejected",
                staff_comment=comment,
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка:\n{e}")
            return

        self.reload()

    def _cancel(self):
        req = self._selected_request()
        if not req:
            return

        if QMessageBox.question(self, "Отмена", f"Отменить заявку #{req.id}?") != QMessageBox.StandardButton.Yes:
            return

        try:
            set_request_status(
                user_id=self.user.id,
                role_code=self.user.role_code,
                request_id=req.id,
                status="cancelled",
            )
        except Exception as e:
            QMessageBox.critical(self, "Заявки", f"Ошибка:\n{e}")
            return

        self.reload()

    def _open_details(self):
        # Быстрый просмотр: пока просто показывает message/staff_comment
        req = self._selected_request()
        if not req:
            return

        text = (
            f"Заявка #{req.id}\n\n"
            f"Статус: {req.status}\n"
            f"Учреждение: {req.org_name}\n"
            f"Площадка: {req.venue_name}\n"
            f"Дата: {req.desired_date:%d.%m.%Y}\n"
            f"Время: {req.desired_start:%H:%M}–{req.desired_end:%H:%M}\n\n"
            f"Клиент: {req.contact_name}\n"
            f"Телефон: {req.contact_phone or '—'}\n\n"
            f"Комментарий клиента:\n{req.message or '—'}\n\n"
            f"Комментарий сотрудника:\n{req.staff_comment or '—'}\n"
        )
        QMessageBox.information(self, "Заявка", text)
