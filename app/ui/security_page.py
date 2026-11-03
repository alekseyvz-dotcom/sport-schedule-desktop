# app/ui/security_page.py
"""
Раздел «Служба безопасности» (ТЗ, п. 1).

СБ самостоятельно вносит по контрагентам (ПД):
  • список спортсменов группы
  • согласованный список автомобилей организованных групп

Доступ:
  • раздел выдаётся в настройках пользователя (галочка «Служба безопасности»);
  • учреждения — из прав пользователя на учреждения;
  • роль admin видит всё.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.security_service import (
    TenantSecuritySummary,
    add_athlete,
    add_vehicle,
    delete_athlete,
    delete_vehicle,
    list_athletes,
    list_security_org_ids,
    list_tenants_for_org,
    list_vehicles,
    normalize_plate,
    update_athlete,
    update_vehicle,
)
from app.services.users_service import AuthUser


def _qdate_or_none(edit: QDateEdit) -> Optional[date]:
    """QDateEdit с пустым значением возвращает невалидную дату — это None."""
    qd = edit.date()
    if qd.isNull() or qd.year() <= 1900:
        return None
    return date(qd.year(), qd.month(), qd.day())


def _set_qdate(edit: QDateEdit, value: Optional[date]) -> None:
    if value is None:
        edit.setDate(QDate(1900, 1, 1))
        edit.setSpecialValueText("—")
    else:
        edit.setDate(QDate(value.year, value.month, value.day))


# ──────────────────────────────────────────────────────────────────────────────
# диалог: спортсмен
# ──────────────────────────────────────────────────────────────────────────────

class AthleteDialog(QDialog):
    def __init__(self, parent=None, athlete=None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Спортсмен")
        self.setModal(True)
        self.setMinimumWidth(480)

        self.ed_name = QLineEdit(getattr(athlete, "full_name", "") or "")
        self.ed_name.setPlaceholderText("Фамилия Имя Отчество")

        self.dt_birth = QDateEdit()
        self.dt_birth.setCalendarPopup(True)
        self.dt_birth.setDisplayFormat("dd.MM.yyyy")
        _set_qdate(self.dt_birth, getattr(athlete, "birth_date", None))

        self.ed_doc = QLineEdit(getattr(athlete, "document_no", "") or "")
        self.ed_doc.setPlaceholderText("Паспорт / свидетельство (необязательно)")

        self.ed_comment = QTextEdit()
        self.ed_comment.setPlainText(getattr(athlete, "comment", "") or "")
        self.ed_comment.setMaximumHeight(80)

        self.cb_active = QCheckBox("Активен")
        self.cb_active.setChecked(bool(getattr(athlete, "is_active", True)))

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addRow("ФИО *:", self.ed_name)
        form.addRow("Дата рождения:", self.dt_birth)
        form.addRow("Документ:", self.ed_doc)
        form.addRow("Комментарий:", self.ed_comment)
        form.addRow("", self.cb_active)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _on_ok(self) -> None:
        if not self.ed_name.text().strip():
            QMessageBox.warning(self, "Спортсмен", "Укажите ФИО.")
            self.ed_name.setFocus()
            return
        if self.dt_birth.date().year() > date.today().year:
            QMessageBox.warning(self, "Спортсмен", "Дата рождения в будущем.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "full_name": self.ed_name.text().strip(),
            "birth_date": _qdate_or_none(self.dt_birth),
            "document_no": self.ed_doc.text().strip() or None,
            "comment": self.ed_comment.toPlainText().strip() or None,
            "is_active": self.cb_active.isChecked(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# диалог: автомобиль
# ──────────────────────────────────────────────────────────────────────────────

class VehicleDialog(QDialog):
    def __init__(self, parent=None, vehicle=None):
        super().__init__(parent)
        self.setObjectName("dialog")
        self.setWindowTitle("Автомобиль")
        self.setModal(True)
        self.setMinimumWidth(520)

        self.ed_plate = QLineEdit(getattr(vehicle, "plate_no", "") or "")
        self.ed_plate.setPlaceholderText("А123ВС77")
        self.ed_plate.textChanged.connect(self._on_plate_changed)

        self.lbl_plate_hint = QLabel("")
        self.lbl_plate_hint.setObjectName("scheduleMeta")

        self.ed_brand = QLineEdit(getattr(vehicle, "brand_model", "") or "")
        self.ed_brand.setPlaceholderText("Например: Ford Transit")

        self.ed_driver = QLineEdit(getattr(vehicle, "driver_name", "") or "")
        self.ed_driver.setPlaceholderText("ФИО водителя")

        self.sp_seats = QComboBox()
        self.sp_seats.addItem("—", None)
        for n in range(2, 61):
            self.sp_seats.addItem(str(n), n)
        seats = getattr(vehicle, "seats", None)
        if seats:
            idx = self.sp_seats.findData(int(seats))
            if idx >= 0:
                self.sp_seats.setCurrentIndex(idx)

        self.dt_from = QDateEdit()
        self.dt_from.setCalendarPopup(True)
        self.dt_from.setDisplayFormat("dd.MM.yyyy")
        _set_qdate(self.dt_from, getattr(vehicle, "pass_valid_from", None))

        self.dt_to = QDateEdit()
        self.dt_to.setCalendarPopup(True)
        self.dt_to.setDisplayFormat("dd.MM.yyyy")
        _set_qdate(self.dt_to, getattr(vehicle, "pass_valid_to", None))

        self.ed_comment = QTextEdit()
        self.ed_comment.setPlainText(getattr(vehicle, "comment", "") or "")
        self.ed_comment.setMaximumHeight(70)

        self.cb_active = QCheckBox("Согласован")
        self.cb_active.setChecked(bool(getattr(vehicle, "is_active", True)))

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addRow("Госномер *:", self.ed_plate)
        form.addRow("", self.lbl_plate_hint)
        form.addRow("Марка/модель:", self.ed_brand)
        form.addRow("Водитель:", self.ed_driver)
        form.addRow("Мест:", self.sp_seats)
        form.addRow("Пропуск с:", self.dt_from)
        form.addRow("Пропуск по:", self.dt_to)
        form.addRow("Комментарий:", self.ed_comment)
        form.addRow("", self.cb_active)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.addLayout(form)
        lay.addWidget(buttons)

        self._on_plate_changed()

    def _on_plate_changed(self) -> None:
        plate = normalize_plate(self.ed_plate.text())
        lower = self.ed_plate.text().strip().lower()
        if plate and lower in ("нет", "без", "нет авто", "пешком", "—", "-"):
            self.lbl_plate_hint.setText(
                "Отмечено, что транспорта нет — сохранится как «БЕЗ АВТО»."
            )
        elif len(plate) == 9:
            self.lbl_plate_hint.setText(f"Будет сохранено: {plate}")
        else:
            self.lbl_plate_hint.setText(
                "Номер хранится в верхнем регистре без пробелов и дефисов."
            )

    def _on_ok(self) -> None:
        if not normalize_plate(self.ed_plate.text()):
            QMessageBox.warning(self, "Автомобиль", "Укажите госномер.")
            self.ed_plate.setFocus()
            return
        d_from = _qdate_or_none(self.dt_from)
        d_to = _qdate_or_none(self.dt_to)
        if d_from and d_to and d_to < d_from:
            QMessageBox.warning(
                self, "Автомобиль",
                "Срок пропуска: дата «по» раньше даты «с».",
            )
            return
        self.accept()

    def values(self) -> dict:
        seats = self.sp_seats.currentData()
        return {
            "plate_no": normalize_plate(self.ed_plate.text()),
            "brand_model": self.ed_brand.text().strip() or None,
            "driver_name": self.ed_driver.text().strip() or None,
            "seats": int(seats) if seats else None,
            "pass_valid_from": _qdate_or_none(self.dt_from),
            "pass_valid_to": _qdate_or_none(self.dt_to),
            "comment": self.ed_comment.toPlainText().strip() or None,
            "is_active": self.cb_active.isChecked(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# страница
# ──────────────────────────────────────────────────────────────────────────────

class SecurityPage(QWidget):
    """
    Раздел СБ: слева контрагенты учреждения, справа два реестра.
    """

    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")

        self._user = user
        self._role = (getattr(user, "role_code", "") or "").strip().lower()
        self._is_admin = self._role == "admin"

        self._orgs: List = []
        self._tenants: List[TenantSecuritySummary] = []
        self._current_tenant: Optional[TenantSecuritySummary] = None

        # ── шапка ──────────────────────────────────────────────────────────
        lbl_title = QLabel("Служба безопасности")
        lbl_title.setObjectName("sectionTitle")

        self.cmb_org = QComboBox()
        self.cmb_org.setMinimumWidth(260)
        self.cmb_org.currentIndexChanged.connect(self._on_org_changed)

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск контрагента: имя / телефон")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)
        self.ed_search.textChanged.connect(self._on_search_changed)

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.cb_presence = QCheckBox("Только бывающие здесь")
        self.cb_presence.setChecked(True)
        self.cb_presence.setToolTip(
            "Показывать только тех, у кого есть правила или занятия "
            "на площадках выбранного учреждения"
        )
        self.cb_presence.stateChanged.connect(lambda *_: self.reload())

        self.btn_refresh = QPushButton("Обновить")
        self.btn_refresh.clicked.connect(self.reload)

        top = QHBoxLayout()
        top.setContentsMargins(12, 10, 12, 6)
        top.setSpacing(8)
        top.addWidget(lbl_title)
        top.addWidget(QLabel("Учреждение:"))
        top.addWidget(self.cmb_org, 1)
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cb_presence)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_refresh)

        # ── левый список контрагентов ──────────────────────────────────────
        self.tbl_tenants = QTableWidget(0, 4)
        self.tbl_tenants.setObjectName("securityTenantsTable")
        self.tbl_tenants.setHorizontalHeaderLabels(
            ["Контрагент", "Спортсмены", "Автомобили", ""]
        )
        self.tbl_tenants.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_tenants.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_tenants.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_tenants.setShowGrid(False)
        self.tbl_tenants.verticalHeader().setVisible(False)
        self.tbl_tenants.setAlternatingRowColors(False)
        self.tbl_tenants.itemSelectionChanged.connect(self._on_tenant_selected)

        h1 = self.tbl_tenants.horizontalHeader()
        h1.setHighlightSections(False)
        h1.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h1.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h1.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h1.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.lbl_tenant_hint = QLabel("Выберите контрагента слева")
        self.lbl_tenant_hint.setObjectName("scheduleMeta")
        self.lbl_tenant_hint.setWordWrap(True)

        left = QWidget(self)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)
        left_lay.addWidget(self.tbl_tenants, 1)
        left_lay.addWidget(self.lbl_tenant_hint)

        # ── правая часть: два реестра ──────────────────────────────────────
        self.lbl_right_title = QLabel("Данные не выбраны")
        self.lbl_right_title.setObjectName("sectionTitle")
        self.lbl_right_title.setWordWrap(True)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_athletes_tab(), "Спортсмены")
        self.tabs.addTab(self._build_vehicles_tab(), "Автомобили")

        right = QWidget(self)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)
        right_lay.addWidget(self.lbl_right_title)
        right_lay.addWidget(self.tabs, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)
        root.addLayout(top)
        root.addWidget(splitter, 1)

        self._apply_ui_access()
        self._load_orgs()

    # ── построение вкладок ─────────────────────────────────────────────────

    def _build_athletes_tab(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)

        self.tbl_athletes = QTableWidget(0, 4)
        self.tbl_athletes.setObjectName("securityAthletesTable")
        self.tbl_athletes.setHorizontalHeaderLabels(["ФИО", "Дата рождения", "Документ", "Активен"])
        self.tbl_athletes.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_athletes.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_athletes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_athletes.setShowGrid(False)
        self.tbl_athletes.verticalHeader().setVisible(False)
        self.tbl_athletes.doubleClicked.connect(lambda *_: self._on_edit_athlete())

        h = self.tbl_athletes.horizontalHeader()
        h.setHighlightSections(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.btn_ath_add = QPushButton("Добавить")
        self.btn_ath_edit = QPushButton("Изменить")
        self.btn_ath_del = QPushButton("Удалить")
        self.btn_ath_add.clicked.connect(self._on_add_athlete)
        self.btn_ath_edit.clicked.connect(self._on_edit_athlete)
        self.btn_ath_del.clicked.connect(self._on_delete_athlete)

        self.lbl_ath_count = QLabel("")
        self.lbl_ath_count.setObjectName("scheduleMeta")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.btn_ath_add)
        row.addWidget(self.btn_ath_edit)
        row.addWidget(self.btn_ath_del)
        row.addStretch(1)
        row.addWidget(self.lbl_ath_count)

        lay.addWidget(self.tbl_athletes, 1)
        lay.addLayout(row)
        return w

    def _build_vehicles_tab(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)

        self.tbl_vehicles = QTableWidget(0, 7)
        self.tbl_vehicles.setObjectName("securityVehiclesTable")
        self.tbl_vehicles.setHorizontalHeaderLabels(
            ["Госномер", "Марка / модель", "Водитель", "Мест", "Пропуск", "Согласовал", "Активен"]
        )
        self.tbl_vehicles.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_vehicles.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_vehicles.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_vehicles.setShowGrid(False)
        self.tbl_vehicles.verticalHeader().setVisible(False)
        self.tbl_vehicles.doubleClicked.connect(lambda *_: self._on_edit_vehicle())

        h = self.tbl_vehicles.horizontalHeader()
        h.setHighlightSections(False)
        for c in range(self.tbl_vehicles.columnCount()):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.btn_veh_add = QPushButton("Добавить")
        self.btn_veh_edit = QPushButton("Изменить")
        self.btn_veh_del = QPushButton("Удалить")
        self.btn_veh_add.clicked.connect(self._on_add_vehicle)
        self.btn_veh_edit.clicked.connect(self._on_edit_vehicle)
        self.btn_veh_del.clicked.connect(self._on_delete_vehicle)

        self.lbl_veh_count = QLabel("")
        self.lbl_veh_count.setObjectName("scheduleMeta")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.btn_veh_add)
        row.addWidget(self.btn_veh_edit)
        row.addWidget(self.btn_veh_del)
        row.addStretch(1)
        row.addWidget(self.lbl_veh_count)

        lay.addWidget(self.tbl_vehicles, 1)
        lay.addLayout(row)
        return w

    # ── доступ ─────────────────────────────────────────────────────────────

    def _can_edit(self) -> bool:
        return bool(self.cmb_org.currentData()) and bool(self._current_tenant)

    def _apply_ui_access(self) -> None:
        editable = self._can_edit()
        for b in (
            self.btn_ath_add, self.btn_ath_edit, self.btn_ath_del,
            self.btn_veh_add, self.btn_veh_edit, self.btn_veh_del,
        ):
            b.setEnabled(editable)

    # ── загрузка ───────────────────────────────────────────────────────────

    def _load_orgs(self) -> None:
        try:
            org_ids = list_security_org_ids(
                user_id=int(self._user.id), role_code=str(self._user.role_code)
            )
            from app.services.ref_service import list_active_orgs_by_ids

            self._orgs = list(list_active_orgs_by_ids(org_ids))
        except Exception as e:
            QMessageBox.critical(
                self, "Служба безопасности", f"Ошибка загрузки учреждений:\n{e}"
            )
            self._orgs = []

        self.cmb_org.blockSignals(True)
        self.cmb_org.clear()
        for o in self._orgs:
            self.cmb_org.addItem(o.name, int(o.id))
        self.cmb_org.blockSignals(False)

        if not self._orgs:
            self.lbl_tenant_hint.setText(
                "Нет доступных учреждений. Обратитесь к администратору."
            )
            return

        self._on_org_changed()

    def _on_search_changed(self, *_):
        # поиск по Enter и кнопке; по вводу не дёргаем БД
        pass

    def _on_org_changed(self, *_) -> None:
        self._current_tenant = None
        self.lbl_right_title.setText("Данные не выбраны")
        self.tbl_athletes.setRowCount(0)
        self.tbl_vehicles.setRowCount(0)
        self.reload()

    def reload(self) -> None:
        org_id = self.cmb_org.currentData()
        if org_id is None:
            self.tbl_tenants.setRowCount(0)
            self.lbl_tenant_hint.setText("Учреждение не выбрано.")
            self._apply_ui_access()
            return

        try:
            self._tenants = list_tenants_for_org(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=int(org_id),
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
                only_with_presence=self.cb_presence.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Служба безопасности", f"Ошибка загрузки контрагентов:\n{e}"
            )
            self._tenants = []

        self._fill_tenants()

        if not self._tenants:
            self.lbl_tenant_hint.setText(
                "Контрагентов не найдено. "
                "Снимите «Только бывающие здесь» или измените поиск."
            )
        else:
            self.lbl_tenant_hint.setText(
                f"Контрагентов: {len(self._tenants)}. Выберите строку."
            )

        # восстановим выбор, если контрагент остался в списке
        if self._current_tenant is not None:
            for r, t in enumerate(self._tenants):
                if t.tenant_id == self._current_tenant.tenant_id:
                    self.tbl_tenants.selectRow(r)
                    return
            self._current_tenant = None
            self._clear_registries()

    def _fill_tenants(self) -> None:
        tbl = self.tbl_tenants
        tbl.blockSignals(True)
        tbl.setRowCount(len(self._tenants))

        for r, t in enumerate(self._tenants):
            it_name = QTableWidgetItem(t.tenant_name)
            it_name.setData(Qt.ItemDataRole.UserRole, t)
            tbl.setItem(r, 0, it_name)

            ath = QTableWidgetItem(f"{t.athletes_active} / {t.athletes_total}")
            ath.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if t.athletes_total == 0:
                ath.setForeground(QColor(226, 232, 240, 105))
            tbl.setItem(r, 1, ath)

            veh = QTableWidgetItem(f"{t.vehicles_active} / {t.vehicles_total}")
            veh.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if t.vehicles_total == 0:
                veh.setForeground(QColor(226, 232, 240, 105))
            tbl.setItem(r, 2, veh)

            mark = QTableWidgetItem("" if (t.athletes_total or t.vehicles_total) else "не заполнено")
            mark.setForeground(QColor(245, 158, 11, 200))
            tbl.setItem(r, 3, mark)

        tbl.blockSignals(False)

    def _clear_registries(self) -> None:
        self.lbl_right_title.setText("Данные не выбраны")
        self.tbl_athletes.setRowCount(0)
        self.tbl_vehicles.setRowCount(0)
        self.lbl_ath_count.setText("")
        self.lbl_veh_count.setText("")
        self._apply_ui_access()

    # ── выбор контрагента ──────────────────────────────────────────────────

    def _on_tenant_selected(self) -> None:
        row = self.tbl_tenants.currentRow()
        if row < 0:
            self._current_tenant = None
            self._clear_registries()
            return

        item = self.tbl_tenants.item(row, 0)
        t = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(t, TenantSecuritySummary):
            self._current_tenant = None
            self._clear_registries()
            return

        self._current_tenant = t
        self.lbl_right_title.setText(f"{t.tenant_name}")
        self._load_athletes()
        self._load_vehicles()
        self._apply_ui_access()

    def _current_tenant_id(self) -> Optional[int]:
        return self._current_tenant.tenant_id if self._current_tenant else None

    def _current_org_id(self) -> Optional[int]:
        data = self.cmb_org.currentData()
        return int(data) if data is not None else None

    # ── спортсмены ─────────────────────────────────────────────────────────

    def _load_athletes(self) -> None:
        org_id = self._current_org_id()
        tenant_id = self._current_tenant_id()
        if org_id is None or tenant_id is None:
            self.tbl_athletes.setRowCount(0)
            self.lbl_ath_count.setText("")
            return

        try:
            rows = list_athletes(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                tenant_id=tenant_id,
                include_inactive=True,
            )
        except Exception as e:
            QMessageBox.critical(self, "Спортсмены", f"Ошибка загрузки:\n{e}")
            rows = []

        self.tbl_athletes.setRowCount(len(rows))
        for r, a in enumerate(rows):
            it = QTableWidgetItem(a.full_name)
            it.setData(Qt.ItemDataRole.UserRole, a)
            if not a.is_active:
                it.setForeground(QColor(226, 232, 240, 120))
            self.tbl_athletes.setItem(r, 0, it)

            self.tbl_athletes.setItem(
                r, 1,
                QTableWidgetItem(a.birth_date.strftime("%d.%m.%Y") if a.birth_date else "—"),
            )
            self.tbl_athletes.setItem(r, 2, QTableWidgetItem(a.document_no or "—"))
            self.tbl_athletes.setItem(
                r, 3, QTableWidgetItem("да" if a.is_active else "нет")
            )

        active = sum(1 for a in rows if a.is_active)
        self.lbl_ath_count.setText(f"Всего: {len(rows)} · активных: {active}")

    def _selected_athlete(self):
        row = self.tbl_athletes.currentRow()
        if row < 0:
            return None
        it = self.tbl_athletes.item(row, 0)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _on_add_athlete(self) -> None:
        org_id = self._current_org_id()
        tenant_id = self._current_tenant_id()
        if org_id is None or tenant_id is None:
            return

        dlg = AthleteDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        v = dlg.values()
        try:
            add_athlete(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                tenant_id=tenant_id,
                full_name=v["full_name"],
                birth_date=v["birth_date"],
                document_no=v["document_no"],
                comment=v["comment"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Спортсмены", f"Не удалось сохранить:\n{e}")
            return

        self._load_athletes()
        self.reload()

    def _on_edit_athlete(self) -> None:
        a = self._selected_athlete()
        if not a:
            QMessageBox.information(self, "Спортсмены", "Выберите спортсмена.")
            return

        org_id = self._current_org_id()
        if org_id is None:
            return

        dlg = AthleteDialog(self, athlete=a)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        v = dlg.values()
        try:
            update_athlete(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                athlete_id=int(a.id),
                full_name=v["full_name"],
                birth_date=v["birth_date"],
                document_no=v["document_no"],
                comment=v["comment"],
                is_active=v["is_active"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Спортсмены", f"Не удалось сохранить:\n{e}")
            return

        self._load_athletes()
        self.reload()

    def _on_delete_athlete(self) -> None:
        a = self._selected_athlete()
        if not a:
            QMessageBox.information(self, "Спортсмены", "Выберите спортсмена.")
            return

        org_id = self._current_org_id()
        if org_id is None:
            return

        if QMessageBox.question(
            self, "Спортсмены",
            f"Удалить «{a.full_name}» из списка?\n\nДействие необратимо.",
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            delete_athlete(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                athlete_id=int(a.id),
            )
        except Exception as e:
            QMessageBox.critical(self, "Спортсмены", f"Не удалось удалить:\n{e}")
            return

        self._load_athletes()
        self.reload()

    # ── автомобили ─────────────────────────────────────────────────────────

    def _load_vehicles(self) -> None:
        org_id = self._current_org_id()
        tenant_id = self._current_tenant_id()
        if org_id is None or tenant_id is None:
            self.tbl_vehicles.setRowCount(0)
            self.lbl_veh_count.setText("")
            return

        try:
            rows = list_vehicles(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                tenant_id=tenant_id,
                include_inactive=True,
            )
        except Exception as e:
            QMessageBox.critical(self, "Автомобили", f"Ошибка загрузки:\n{e}")
            rows = []

        self.tbl_vehicles.setRowCount(len(rows))
        for r, v in enumerate(rows):
            it = QTableWidgetItem(v.plate_no)
            it.setData(Qt.ItemDataRole.UserRole, v)
            f = QFont(it.font())
            f.setBold(True)
            it.setFont(f)
            if not v.is_active:
                it.setForeground(QColor(226, 232, 240, 120))
            self.tbl_vehicles.setItem(r, 0, it)

            self.tbl_vehicles.setItem(r, 1, QTableWidgetItem(v.brand_model or "—"))
            self.tbl_vehicles.setItem(r, 2, QTableWidgetItem(v.driver_name or "—"))
            self.tbl_vehicles.setItem(
                r, 3, QTableWidgetItem(str(v.seats) if v.seats else "—")
            )

            if v.pass_valid_from or v.pass_valid_to:
                s = v.pass_valid_from.strftime("%d.%m.%y") if v.pass_valid_from else "…"
                e = v.pass_valid_to.strftime("%d.%m.%y") if v.pass_valid_to else "…"
                period = f"{s} — {e}"
            else:
                period = "—"
            self.tbl_vehicles.setItem(r, 4, QTableWidgetItem(period))

            approved = "—"
            if v.approved_at:
                stamp = v.approved_at.strftime("%d.%m.%y")
                who = v.approved_by_name or "—"
                approved = f"{who}, {stamp}"
            self.tbl_vehicles.setItem(r, 5, QTableWidgetItem(approved))

            self.tbl_vehicles.setItem(
                r, 6, QTableWidgetItem("да" if v.is_active else "нет")
            )

        active = sum(1 for v in rows if v.is_active)
        self.lbl_veh_count.setText(f"Всего: {len(rows)} · согласовано: {active}")

    def _selected_vehicle(self):
        row = self.tbl_vehicles.currentRow()
        if row < 0:
            return None
        it = self.tbl_vehicles.item(row, 0)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _on_add_vehicle(self) -> None:
        org_id = self._current_org_id()
        tenant_id = self._current_tenant_id()
        if org_id is None or tenant_id is None:
            return

        dlg = VehicleDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        v = dlg.values()
        try:
            add_vehicle(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                tenant_id=tenant_id,
                plate_no=v["plate_no"],
                brand_model=v["brand_model"],
                driver_name=v["driver_name"],
                seats=v["seats"],
                pass_valid_from=v["pass_valid_from"],
                pass_valid_to=v["pass_valid_to"],
                comment=v["comment"],
                approved=v["is_active"],
            )
        except Exception as e:
            msg = str(e)
            if "ux_tenant_vehicles_org_plate" in msg or "duplicate key" in msg.lower():
                QMessageBox.warning(
                    self, "Автомобили",
                    "Такой номер уже есть в списке этого учреждения.",
                )
            else:
                QMessageBox.critical(self, "Автомобили", f"Не удалось сохранить:\n{e}")
            return

        self._load_vehicles()
        self.reload()

    def _on_edit_vehicle(self) -> None:
        v = self._selected_vehicle()
        if not v:
            QMessageBox.information(self, "Автомобили", "Выберите автомобиль.")
            return

        org_id = self._current_org_id()
        if org_id is None:
            return

        dlg = VehicleDialog(self, vehicle=v)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.values()
        try:
            update_vehicle(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                vehicle_id=int(v.id),
                plate_no=data["plate_no"],
                brand_model=data["brand_model"],
                driver_name=data["driver_name"],
                seats=data["seats"],
                pass_valid_from=data["pass_valid_from"],
                pass_valid_to=data["pass_valid_to"],
                comment=data["comment"],
                is_active=data["is_active"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Автомобили", f"Не удалось сохранить:\n{e}")
            return

        self._load_vehicles()
        self.reload()

    def _on_delete_vehicle(self) -> None:
        v = self._selected_vehicle()
        if not v:
            QMessageBox.information(self, "Автомобили", "Выберите автомобиль.")
            return

        org_id = self._current_org_id()
        if org_id is None:
            return

        if QMessageBox.question(
            self, "Автомобили",
            f"Удалить «{v.plate_no}» из согласованного списка?\n\nДействие необратимо.",
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            delete_vehicle(
                user_id=int(self._user.id),
                role_code=str(self._user.role_code),
                org_id=org_id,
                vehicle_id=int(v.id),
            )
        except Exception as e:
            QMessageBox.critical(self, "Автомобили", f"Не удалось удалить:\n{e}")
            return

        self._load_vehicles()
        self.reload()
