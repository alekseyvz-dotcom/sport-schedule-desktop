# app/ui/client_info_dialog.py
"""
Карточка просмотра клиента из расписания (ТЗ, п. 7).

Открывается по двойному щелчку на занятии в месячной визуализации:
показывает договор, правила, условия и комментарии, не требуя
переходить во вкладку «Контрагенты».

Диалог только читает данные.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.fit_screen import fit_and_scroll

APP_TZ = timezone(timedelta(hours=3))
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _fmt_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.astimezone(APP_TZ).strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


def _fmt_bool(value) -> str:
    return "Да" if value else "Нет"


def _ro_line(text: str) -> QLabel:
    lbl = QLabel(text if text else "—")
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


class ClientInfoDialog(QDialog):
    """
    Просмотр клиента (ПД) или группы ГЗ.

    Параметры:
        tenant      — объект Tenant (для ПД)
        gz_group    — словарь/объект группы ГЗ (для ГЗ)
    """

    def __init__(
        self,
        parent,
        *,
        user_id: int,
        role_code: str,
        tenant=None,
        gz_group=None,
        booking=None,
    ):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setModal(True)

        self._user_id = int(user_id)
        self._role_code = str(role_code)
        self._tenant = tenant
        self._gz = gz_group
        self._booking = booking

        self._is_gz = tenant is None and gz_group is not None

        if self._is_gz:
            self.setWindowTitle("Группа ГЗ")
            title_text = self._gz_title()
            subtitle = "Государственное задание"
        else:
            self.setWindowTitle(f"Клиент: {getattr(tenant, 'name', '')}")
            title_text = getattr(tenant, "name", "") or "Без названия"
            subtitle = self._tenant_subtitle()

        # ── шапка ──────────────────────────────────────────────────────────
        lbl_title = QLabel(title_text)
        lbl_title.setObjectName("sectionTitle")
        lbl_title.setWordWrap(True)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setObjectName("scheduleMeta")
        lbl_sub.setWordWrap(True)

        if booking is not None:
            start = booking.starts_at.astimezone(APP_TZ)
            end = booking.ends_at.astimezone(APP_TZ)
            lbl_slot = QLabel(
                f"Занятие: {start.strftime('%d.%m.%Y')} "
                f"({WEEKDAYS[start.weekday()]}) · "
                f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} · "
                f"{(getattr(booking, 'venue_unit_name', '') or 'объект целиком')}"
            )
            lbl_slot.setObjectName("scheduleMeta")
            lbl_slot.setWordWrap(True)
        else:
            lbl_slot = None

        # ── вкладки ────────────────────────────────────────────────────────
        self.tabs = QTabWidget(self)
        if self._is_gz:
            self.tabs.addTab(self._tab_gz_main(), "Группа")
            self.tabs.addTab(self._tab_gz_rules(), "Правила")
        else:
            self.tabs.addTab(self._tab_tenant_main(), "Данные")
            self.tabs.addTab(self._tab_contracts(), "Договоры")
            self.tabs.addTab(self._tab_tenant_rules(), "Правила")

        buttons = QDialogButtonBox(self)
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.reject)
        buttons.addButton(btn_close, QDialogButtonBox.ButtonRole.RejectRole)

        if not self._is_gz and tenant is not None:
            btn_open = QPushButton("Открыть полную карточку")
            btn_open.clicked.connect(self._on_open_full)
            buttons.addButton(btn_open, QDialogButtonBox.ButtonRole.ActionRole)

        self.open_full_requested = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(8)
        root.addWidget(lbl_title)
        root.addWidget(lbl_sub)
        if lbl_slot is not None:
            root.addWidget(lbl_slot)
        root.addWidget(self.tabs, 1)
        root.addWidget(buttons)

        fit_and_scroll(self, width=880, height=620)

    # ── вспомогательное ────────────────────────────────────────────────────

    def _on_open_full(self) -> None:
        self.open_full_requested = True
        self.accept()

    def _tenant_subtitle(self) -> str:
        t = self._tenant
        parts: List[str] = []
        kind = (getattr(t, "tenant_kind", "") or "").strip()
        parts.append("Физлицо" if kind == "person" else "Юрлицо")
        rent = (getattr(t, "rent_kind", "") or "").strip()
        if rent:
            parts.append("долгосрочно" if rent == "long_term" else "разово")
        status = (getattr(t, "status", "") or "").strip()
        if status:
            parts.append({"active": "активен", "paused": "на паузе", "closed": "закрыт"}.get(status, status))
        if not getattr(t, "is_active", True):
            parts.append("в архиве")
        return " · ".join(p for p in parts if p)

    def _gz_title(self) -> str:
        g = self._gz
        if isinstance(g, dict):
            coach = g.get("coach_name") or ""
            year = g.get("group_year") or ""
        else:
            coach = getattr(g, "coach_name", "") or ""
            year = getattr(g, "group_year", "") or ""
        return " — ".join(x for x in (coach, year) if x) or "Группа ГЗ"

    def _make_table(self, headers: List[str]) -> QTableWidget:
        tbl = QTableWidget()
        tbl.setObjectName("scheduleList")
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)

        hdr = tbl.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return tbl

    @staticmethod
    def _cell(text: str, *, dim: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if dim:
            item.setForeground(QColor(226, 232, 240, 120))
        return item

    # ── вкладки: контрагент ────────────────────────────────────────────────

    def _tab_tenant_main(self) -> QWidget:
        t = self._tenant
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        gb = QGroupBox("Основное")
        form = QFormLayout(gb)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        form.addRow("Название:", _ro_line(getattr(t, "name", "") or ""))
        form.addRow("ИНН:", _ro_line(getattr(t, "inn", "") or ""))
        form.addRow("Телефон:", _ro_line(getattr(t, "phone", "") or ""))
        form.addRow("Контакт:", _ro_line(getattr(t, "contact_name", "") or ""))
        form.addRow("Обязательства:", _ro_line(getattr(t, "obligation_kind", "") or ""))

        gb_contract = QGroupBox("Договор (текущий)")
        cf = QFormLayout(gb_contract)
        cf.setHorizontalSpacing(14)
        cf.setVerticalSpacing(8)
        cf.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        cf.addRow("Номер:", _ro_line(getattr(t, "contract_no", "") or ""))
        cf.addRow("Дата:", _ro_line(_fmt_date(getattr(t, "contract_date", None))))
        cf.addRow(
            "Срок:",
            _ro_line(
                f"{_fmt_date(getattr(t, 'contract_valid_from', None))} — "
                f"{_fmt_date(getattr(t, 'contract_valid_to', None))}"
            ),
        )
        cf.addRow("Подписан:", _ro_line(_fmt_bool(getattr(t, "contract_signed", False))))
        cf.addRow("В 1С:", _ro_line(_fmt_bool(getattr(t, "attached_in_1c", False))))
        cf.addRow("ДС:", _ro_line(_fmt_bool(getattr(t, "has_ds", False))))

        gb_notes = QGroupBox("Комментарии")
        nl = QVBoxLayout(gb_notes)
        nl.setContentsMargins(12, 16, 12, 12)
        nl.setSpacing(6)

        for caption, value in (
            ("Комментарий", getattr(t, "comment", "") or ""),
            ("Примечания", getattr(t, "notes", "") or ""),
        ):
            lbl = QLabel(caption + ":")
            lbl.setObjectName("scheduleMeta")
            nl.addWidget(lbl)
            txt = QTextEdit()
            txt.setPlainText(value or "—")
            txt.setReadOnly(True)
            txt.setMaximumHeight(70)
            nl.addWidget(txt)

        gc = QHBoxLayout()
        gc.setSpacing(10)
        gc.addWidget(gb, 1)
        gc.addWidget(gb_contract, 1)

        lay.addLayout(gc)
        lay.addWidget(gb_notes)
        lay.addStretch(1)
        return w

    def _tab_contracts(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        tbl = self._make_table(["Номер", "Дата", "Срок с", "Срок по", "Подписан", "В 1С", "ДС", "Источник"])

        rows: List[Dict] = []
        error = ""
        try:
            from app.services.tenant_contracts_service import list_contracts

            tenant_id = getattr(self._tenant, "id", None)
            if tenant_id is not None:
                rows = list(list_contracts(
                    user_id=self._user_id,
                    role_code=self._role_code,
                    tenant_id=int(tenant_id),
                ) or [])
            else:
                error = "Карточка не сохранена — история договоров недоступна."
        except Exception as e:
            error = f"Не удалось загрузить историю договоров: {e}"

        if rows:
            tbl.setRowCount(len(rows))
            for r, row in enumerate(rows):
                legacy = bool(row.get("is_legacy"))
                tbl.setItem(r, 0, self._cell(str(row.get("contract_no") or "")))
                tbl.setItem(r, 1, self._cell(_fmt_date(row.get("contract_date"))))
                tbl.setItem(r, 2, self._cell(_fmt_date(row.get("valid_from"))))
                tbl.setItem(r, 3, self._cell(_fmt_date(row.get("valid_to"))))
                tbl.setItem(r, 4, self._cell(_fmt_bool(row.get("contract_signed")), dim=not row.get("contract_signed")))
                tbl.setItem(r, 5, self._cell(_fmt_bool(row.get("attached_in_1c")), dim=not row.get("attached_in_1c")))
                tbl.setItem(r, 6, self._cell(_fmt_bool(row.get("has_ds")), dim=not row.get("has_ds")))
                tbl.setItem(r, 7, self._cell("текущий" if legacy else "добавлен", dim=not legacy))
            tbl.resizeRowsToContents()
            lay.addWidget(tbl, 1)
        else:
            lay.addWidget(tbl, 1)
            note = QLabel(error or "В истории пока нет записей.")
            note.setObjectName("scheduleMeta")
            note.setWordWrap(True)
            lay.addWidget(note)

        return w

    def _tab_tenant_rules(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        tbl = self._make_table(["День", "Время", "Период действия", "Название", "Активно"])

        rows = []
        error = ""
        try:
            from app.services.tenant_rules_service import list_rules_for_tenant

            tenant_id = getattr(self._tenant, "id", None)
            if tenant_id is not None:
                rows = list(list_rules_for_tenant(
                    user_id=self._user_id,
                    role_code=self._role_code,
                    tenant_id=int(tenant_id),
                    include_inactive=True,
                ) or [])
            else:
                error = "Карточка не сохранена — правила недоступны."
        except Exception as e:
            error = f"Не удалось загрузить правила: {e}"

        if rows:
            tbl.setRowCount(len(rows))
            for r, rule in enumerate(rows):
                wd = int(getattr(rule, "weekday", 0) or 0)
                wd_text = WEEKDAYS[wd - 1] if 1 <= wd <= 7 else str(wd)
                active = bool(getattr(rule, "is_active", False))

                tbl.setItem(r, 0, self._cell(wd_text, dim=not active))
                tbl.setItem(r, 1, self._cell(
                    f"{getattr(rule, 'starts_at', '')}–{getattr(rule, 'ends_at', '')}",
                    dim=not active,
                ))
                tbl.setItem(r, 2, self._cell(
                    f"{_fmt_date(getattr(rule, 'valid_from', None))} — "
                    f"{_fmt_date(getattr(rule, 'valid_to', None))}",
                    dim=not active,
                ))
                tbl.setItem(r, 3, self._cell(getattr(rule, "title", "") or "", dim=not active))
                tbl.setItem(r, 4, self._cell("да" if active else "нет", dim=not active))
            tbl.resizeRowsToContents()
            lay.addWidget(tbl, 1)
        else:
            lay.addWidget(tbl, 1)
            note = QLabel(error or "Правила не заданы.")
            note.setObjectName("scheduleMeta")
            note.setWordWrap(True)
            lay.addWidget(note)

        return w

    # ── вкладки: ГЗ ────────────────────────────────────────────────────────

    def _tab_gz_main(self) -> QWidget:
        g = self._gz
        get = (lambda k, d=None: g.get(k, d)) if isinstance(g, dict) else (
            lambda k, d=None: getattr(g, k, d)
        )

        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        gb = QGroupBox("Группа")
        form = QFormLayout(gb)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        form.addRow("Тренер:", _ro_line(str(get("coach_name", "") or "")))
        form.addRow("Год:", _ro_line(str(get("group_year", "") or "")))
        form.addRow("Период с:", _ro_line(_fmt_date(get("period_from"))))
        form.addRow("Период по:", _ro_line(_fmt_date(get("period_to"))))
        form.addRow("Бесплатно:", _ro_line(_fmt_bool(get("is_free", False))))
        form.addRow("Активна:", _ro_line(_fmt_bool(get("is_active", True))))

        gb_notes = QGroupBox("Примечания")
        nl = QVBoxLayout(gb_notes)
        nl.setContentsMargins(12, 16, 12, 12)
        txt = QTextEdit()
        txt.setPlainText(str(get("notes", "") or "—"))
        txt.setReadOnly(True)
        txt.setMaximumHeight(90)
        nl.addWidget(txt)

        lay.addWidget(gb)
        lay.addWidget(gb_notes)
        lay.addStretch(1)
        return w

    def _tab_gz_rules(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        tbl = self._make_table(["День", "Время", "Период действия", "Название", "Активно"])

        rows = []
        error = ""
        try:
            from app.services.gz_rules_service import list_rules_for_group

            gid = (self._gz.get("id") if isinstance(self._gz, dict) else getattr(self._gz, "id", None))
            if gid is not None:
                rows = list(list_rules_for_group(
                    user_id=self._user_id,
                    role_code=self._role_code,
                    gz_group_id=int(gid),
                    include_inactive=True,
                ) or [])
            else:
                error = "Группа не сохранена — правила недоступны."
        except Exception as e:
            error = f"Не удалось загрузить правила: {e}"

        if rows:
            tbl.setRowCount(len(rows))
            for r, rule in enumerate(rows):
                wd = int(getattr(rule, "weekday", 0) or 0)
                wd_text = WEEKDAYS[wd - 1] if 1 <= wd <= 7 else str(wd)
                active = bool(getattr(rule, "is_active", False))

                tbl.setItem(r, 0, self._cell(wd_text, dim=not active))
                tbl.setItem(r, 1, self._cell(
                    f"{getattr(rule, 'starts_at', '')}–{getattr(rule, 'ends_at', '')}",
                    dim=not active,
                ))
                tbl.setItem(r, 2, self._cell(
                    f"{_fmt_date(getattr(rule, 'valid_from', None))} — "
                    f"{_fmt_date(getattr(rule, 'valid_to', None))}",
                    dim=not active,
                ))
                tbl.setItem(r, 3, self._cell(getattr(rule, "title", "") or "", dim=not active))
                tbl.setItem(r, 4, self._cell("да" if active else "нет", dim=not active))
            tbl.resizeRowsToContents()
            lay.addWidget(tbl, 1)
        else:
            lay.addWidget(tbl, 1)
            note = QLabel(error or "Правила не заданы.")
            note.setObjectName("scheduleMeta")
            note.setWordWrap(True)
            lay.addWidget(note)

        return w
