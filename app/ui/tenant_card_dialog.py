from __future__ import annotations

from datetime import date, time, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QTabWidget,
    QWidget,
    QLineEdit,
    QTextEdit,
    QDateEdit,
    QCheckBox,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QAbstractItemView,
)

from app.services.ref_service import list_active_orgs, list_active_venues
from app.services.venue_units_service import list_venue_units
from app.services.tenants_service import Tenant, update_tenant
from app.services.tenant_rules_service import (
    create_rule,
    list_rules_for_tenant,
    TenantRule,
    generate_bookings_for_rule,
)


def _pydate_to_qdate(d: Optional[date]) -> QDate:
    if not d:
        return QDate()
    return QDate(d.year, d.month, d.day)


def _qdate_to_pydate(qd: QDate) -> Optional[date]:
    if not qd.isValid():
        return None
    return date(qd.year(), qd.month(), qd.day())


class TenantCardDialog(QDialog):
    TZ_OFFSET_HOURS = 3
    TZ = timezone(timedelta(hours=TZ_OFFSET_HOURS))

    def __init__(self, parent=None, tenant: Tenant | None = None):
        super().__init__(parent)
        self.setObjectName("dialog")

        if tenant is None:
            raise ValueError("TenantCardDialog требует tenant")
        self.tenant = tenant

        self.setWindowTitle(f"Контрагент: {tenant.name}")
        self.setModal(True)
        self.resize(900, 600)

        self.tabs = QTabWidget(self)

        # --- TAB 1: Данные контрагента ---
        tab_data = QWidget(self.tabs)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.ed_name = QLineEdit(tenant.name)
        self.ed_inn = QLineEdit(tenant.inn or "")
        self.ed_phone = QLineEdit(tenant.phone or "")
        self.ed_email = QLineEdit(tenant.email or "")
        self.ed_comment = QTextEdit(tenant.comment or "")

        self.ed_contact_name = QLineEdit(tenant.contact_name or "")
        self.ed_obligation_kind = QLineEdit(tenant.obligation_kind or "")
        self.ed_contract_no = QLineEdit(tenant.contract_no or "")

        self.dt_contract_date = QDateEdit()
        self.dt_contract_date.setCalendarPopup(True)
        self.dt_contract_date.setDisplayFormat("dd.MM.yyyy")
        self.dt_contract_date.setDate(_pydate_to_qdate(tenant.contract_date))

        self.dt_valid_from = QDateEdit()
        self.dt_valid_from.setCalendarPopup(True)
        self.dt_valid_from.setDisplayFormat("dd.MM.yyyy")
        self.dt_valid_from.setDate(_pydate_to_qdate(tenant.contract_valid_from))

        self.dt_valid_to = QDateEdit()
        self.dt_valid_to.setCalendarPopup(True)
        self.dt_valid_to.setDisplayFormat("dd.MM.yyyy")
        self.dt_valid_to.setDate(_pydate_to_qdate(tenant.contract_valid_to))

        self.ed_docs_delivery = QLineEdit(tenant.docs_delivery_method or "")

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("active", "active")
        self.cmb_status.addItem("paused", "paused")
        self.cmb_status.addItem("closed", "closed")
        idx = self.cmb_status.findData((tenant.status or "active").strip())
        self.cmb_status.setCurrentIndex(idx if idx >= 0 else 0)

        self.cb_signed = QCheckBox("Подписанный договор")
        self.cb_signed.setChecked(bool(tenant.contract_signed))

        self.cb_attached_1c = QCheckBox("Прикреплен в 1С")
        self.cb_attached_1c.setChecked(bool(tenant.attached_in_1c))

        self.cb_has_ds = QCheckBox("ДС")
        self.cb_has_ds.setChecked(bool(tenant.has_ds))

        self.ed_notes = QTextEdit(tenant.notes or "")

        form.addRow("Название *:", self.ed_name)
        form.addRow("ИНН:", self.ed_inn)
        form.addRow("Телефон:", self.ed_phone)
        form.addRow("Email:", self.ed_email)
        form.addRow("Комментарий:", self.ed_comment)

        form.addRow("Контакт:", self.ed_contact_name)
        form.addRow("Вид обязательства:", self.ed_obligation_kind)
        form.addRow("№ договора:", self.ed_contract_no)
        form.addRow("Дата договора:", self.dt_contract_date)
        form.addRow("Срок действия с:", self.dt_valid_from)
        form.addRow("Срок действия по:", self.dt_valid_to)
        form.addRow("Способ передачи документов:", self.ed_docs_delivery)
        form.addRow("Статус:", self.cmb_status)
        form.addRow("", self.cb_signed)
        form.addRow("", self.cb_attached_1c)
        form.addRow("", self.cb_has_ds)
        form.addRow("Примечания:", self.ed_notes)

        self.btn_save = QPushButton("Сохранить")
        self.btn_save.clicked.connect(self._save_tenant)

        data_footer = QHBoxLayout()
        data_footer.addStretch(1)
        data_footer.addWidget(self.btn_save)

        data_root = QVBoxLayout(tab_data)
        data_root.setContentsMargins(12, 12, 12, 12)
        data_root.setSpacing(10)
        data_root.addLayout(form, 1)
        data_root.addLayout(data_footer)

        # --- TAB 2: Договорное расписание ---
        tab_rules = QWidget(self.tabs)
        rules_root = QVBoxLayout(tab_rules)
        rules_root.setContentsMargins(12, 12, 12, 12)
        rules_root.setSpacing(10)

        sel_row = QHBoxLayout()
        sel_row.setContentsMargins(0, 0, 0, 0)
        sel_row.setSpacing(10)

        self.cmb_org = QComboBox()
        self.cmb_venue = QComboBox()
        self.cmb_unit = QComboBox()

        self.cmb_org.currentIndexChanged.connect(self._on_org_changed)
        self.cmb_venue.currentIndexChanged.connect(self._on_venue_changed)

        sel_row.addWidget(self.cmb_org, 2)
        sel_row.addWidget(self.cmb_venue, 3)
        sel_row.addWidget(self.cmb_unit, 3)
        rules_root.addLayout(sel_row)

        f2 = QFormLayout()
        f2.setContentsMargins(0, 0, 0, 0)
        f2.setHorizontalSpacing(12)
        f2.setVerticalSpacing(10)
        f2.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.cmb_weekday = QComboBox()
        for i, name in [(1, "Пн"), (2, "Вт"), (3, "Ср"), (4, "Чт"), (5, "Пт"), (6, "Сб"), (7, "Вс")]:
            self.cmb_weekday.addItem(name, i)

        self.ed_start = QLineEdit("12:00")
        self.ed_end = QLineEdit("14:00")

        self.dt_rule_from = QDateEdit()
        self.dt_rule_from.setCalendarPopup(True)
        self.dt_rule_from.setDisplayFormat("dd.MM.yyyy")

        self.dt_rule_to = QDateEdit()
        self.dt_rule_to.setCalendarPopup(True)
        self.dt_rule_to.setDisplayFormat("dd.MM.yyyy")

        self.dt_rule_from.setDate(
            _pydate_to_qdate(tenant.contract_valid_from) if tenant.contract_valid_from else QDate.currentDate()
        )
        self.dt_rule_to.setDate(
            _pydate_to_qdate(tenant.contract_valid_to) if tenant.contract_valid_to else QDate.currentDate()
        )

        self.ed_rule_title = QLineEdit("Аренда по договору")

        f2.addRow("День недели:", self.cmb_weekday)
        f2.addRow("Время (HH:MM) с:", self.ed_start)
        f2.addRow("Время (HH:MM) по:", self.ed_end)
        f2.addRow("Период с:", self.dt_rule_from)
        f2.addRow("Период по:", self.dt_rule_to)
        f2.addRow("Заголовок:", self.ed_rule_title)

        rules_root.addLayout(f2)

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(10)

        self.btn_add_rule = QPushButton("Добавить правило")
        self.btn_add_rule.clicked.connect(self._add_rule)

        self.btn_gen = QPushButton("Сгенерировать брони по выбранному правилу")
        self.btn_gen.clicked.connect(self._generate_for_selected_rule)

        btns.addWidget(self.btn_add_rule)
        btns.addWidget(self.btn_gen)
        btns.addStretch(1)
        rules_root.addLayout(btns)

        self.tbl_rules = QTableWidget(0, 8)
        self.tbl_rules.setObjectName("tenantRulesTable")
        self.tbl_rules.setHorizontalHeaderLabels(["ID", "Активно", "Unit", "День", "С", "По", "Период", "Title"])
        self.tbl_rules.setColumnHidden(0, True)
        self.tbl_rules.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_rules.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_rules.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_rules.setShowGrid(False)
        self.tbl_rules.setAlternatingRowColors(False)
        self.tbl_rules.verticalHeader().setVisible(False)

        hdr = self.tbl_rules.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        rules_root.addWidget(self.tbl_rules, 1)

        self.tabs.addTab(tab_data, "Карточка")
        self.tabs.addTab(tab_rules, "Договорное расписание")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(self.tabs, 1)

        self._load_orgs()
        self._reload_rules()

    def _load_orgs(self):
        self.cmb_org.blockSignals(True)
        self.cmb_org.clear()
        orgs = list_active_orgs()
        for o in orgs:
            self.cmb_org.addItem(o.name, o.id)
        self.cmb_org.blockSignals(False)
        self._on_org_changed()

    def _on_org_changed(self):
        org_id = self.cmb_org.currentData()
        self.cmb_venue.blockSignals(True)
        self.cmb_venue.clear()
        if org_id is not None:
            venues = list_active_venues(int(org_id))
            for v in venues:
                self.cmb_venue.addItem(v.name, v.id)
        self.cmb_venue.blockSignals(False)
        self._on_venue_changed()

    def _on_venue_changed(self):
        venue_id = self.cmb_venue.currentData()
        self.cmb_unit.blockSignals(True)
        self.cmb_unit.clear()
        if venue_id is not None:
            units = list_venue_units(int(venue_id))
            for u in units:
                self.cmb_unit.addItem(u.name, u.id)
        self.cmb_unit.blockSignals(False)

    def _save_tenant(self):
        try:
            update_tenant(
                self.tenant.id,
                name=self.ed_name.text().strip(),
                inn=self.ed_inn.text().strip(),
                phone=self.ed_phone.text().strip(),
                email=self.ed_email.text().strip(),
                comment=self.ed_comment.toPlainText().strip(),
                contact_name=self.ed_contact_name.text().strip(),
                obligation_kind=self.ed_obligation_kind.text().strip(),
                contract_no=self.ed_contract_no.text().strip(),
                contract_date=_qdate_to_pydate(self.dt_contract_date.date()),
                contract_valid_from=_qdate_to_pydate(self.dt_valid_from.date()),
                contract_valid_to=_qdate_to_pydate(self.dt_valid_to.date()),
                docs_delivery_method=self.ed_docs_delivery.text().strip(),
                status=self.cmb_status.currentData(),
                contract_signed=self.cb_signed.isChecked(),
                attached_in_1c=self.cb_attached_1c.isChecked(),
                has_ds=self.cb_has_ds.isChecked(),
                notes=self.ed_notes.toPlainText().strip(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Контрагент", f"Ошибка сохранения:\n{e}")
            return

        QMessageBox.information(self, "Контрагент", "Сохранено.")

    def _reload_rules(self):
        rules = list_rules_for_tenant(self.tenant.id, include_inactive=True)
        self.tbl_rules.setRowCount(0)

        wd_name = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}

        for r in rules:
            row = self.tbl_rules.rowCount()
            self.tbl_rules.insertRow(row)

            it_id = QTableWidgetItem(str(r.id))
            it_id.setData(Qt.ItemDataRole.UserRole, r)
            self.tbl_rules.setItem(row, 0, it_id)

            it_active = QTableWidgetItem("Да" if r.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_rules.setItem(row, 1, it_active)

            self.tbl_rules.setItem(row, 2, QTableWidgetItem(str(r.venue_unit_id)))
            self.tbl_rules.setItem(row, 3, QTableWidgetItem(wd_name.get(r.weekday, str(r.weekday))))
            self.tbl_rules.setItem(row, 4, QTableWidgetItem(r.starts_at.strftime("%H:%M")))
            self.tbl_rules.setItem(row, 5, QTableWidgetItem(r.ends_at.strftime("%H:%M")))
            self.tbl_rules.setItem(row, 6, QTableWidgetItem(f"{r.valid_from:%d.%m.%Y}–{r.valid_to:%d.%m.%Y}"))
            self.tbl_rules.setItem(row, 7, QTableWidgetItem(r.title))

        self.tbl_rules.resizeColumnsToContents()

    def _parse_hhmm(self, s: str) -> time:
        s = (s or "").strip()
        parts = s.split(":")
        if len(parts) != 2:
            raise ValueError("Время должно быть в формате HH:MM")
        h = int(parts[0])
        m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Некорректное время")
        return time(h, m)

    def _add_rule(self):
        venue_id = self.cmb_venue.currentData()
        unit_id = self.cmb_unit.currentData()
        if venue_id is None or unit_id is None:
            QMessageBox.warning(self, "Правило", "Выберите учреждение, площадку и часть площадки.")
            return

        try:
            starts = self._parse_hhmm(self.ed_start.text())
            ends = self._parse_hhmm(self.ed_end.text())
            valid_from = _qdate_to_pydate(self.dt_rule_from.date())
            valid_to = _qdate_to_pydate(self.dt_rule_to.date())
            if not valid_from or not valid_to:
                raise ValueError("Укажите период действия правила")
            weekday = int(self.cmb_weekday.currentData())
            title = self.ed_rule_title.text().strip()

            rid = create_rule(
                tenant_id=self.tenant.id,
                venue_unit_id=int(unit_id),
                weekday=weekday,
                starts_at=starts,
                ends_at=ends,
                valid_from=valid_from,
                valid_to=valid_to,
                title=title,
            )
        except Exception as e:
            QMessageBox.critical(self, "Правило", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Правило", f"Правило добавлено (id={rid}).")
        self._reload_rules()

    def _selected_rule(self) -> Optional[TenantRule]:
        row = self.tbl_rules.currentRow()
        if row < 0:
            return None
        it = self.tbl_rules.item(row, 0)
        if not it:
            return None
        r = it.data(Qt.ItemDataRole.UserRole)
        return r

    def _generate_for_selected_rule(self):
        r = self._selected_rule()
        if not r:
            QMessageBox.information(self, "Генерация", "Выберите правило в таблице.")
            return

        from app.db import get_conn, put_conn

        conn = None
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT venue_id FROM public.venue_units WHERE id=%s", (int(r.venue_unit_id),))
                row = cur.fetchone()
                if not row:
                    raise ValueError("venue_unit не найден")
                venue_id = int(row[0])
        finally:
            if conn:
                put_conn(conn)

        try:
            created = generate_bookings_for_rule(rule=r, venue_id=venue_id, tz=self.TZ)
        except Exception as e:
            QMessageBox.critical(self, "Генерация", f"Ошибка генерации:\n{e}")
            return

        QMessageBox.information(self, "Генерация", f"Готово. Создано броней: {created}")
