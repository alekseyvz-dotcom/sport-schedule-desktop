# app/ui/orgs_venues_page.py
from __future__ import annotations

import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QLabel,
    QHeaderView,
    QAbstractItemView,
    QSizePolicy,
)

from app.services.users_service import AuthUser
from app.services.access_service import get_org_access

from app.services.orgs_service import (
    list_orgs,
    create_org,
    update_org,
    set_org_active,
    SportOrg,
)
from app.services.venues_service import (
    list_venues,
    create_venue,
    update_venue,
    set_venue_active,
    Venue,
)
from app.services.venue_units_manage_service import apply_units_scheme
from app.ui.org_dialog import OrgDialog
from app.ui.venue_dialog import VenueDialog

from app.ui.closures_manage_dialog import ClosuresManageDialog
from app.ui.venue_seasons_manage_dialog import VenueSeasonsManageDialog

from app.services.org_closures_service import (
    list_org_closures,
    create_org_closure,
    update_org_closure,
    set_org_closure_active,
)

from app.services.venue_closures_service import (
    list_venue_closures,
    create_venue_closure,
    update_venue_closure,
    set_venue_closure_active,
)

# Импорт вспомогательного сервиса статусов
from app.services.venue_status_service import (
    get_venue_statuses,
    get_org_closure_statuses,
)

# Цвета для индикаторов
_COLOR_CLOSURE = QColor("#FF6B6B")       # красноватый — есть закрытия
_COLOR_SEASON  = QColor("#4ECDC4")       # бирюзовый — есть сезонность
_COLOR_BOTH    = QColor("#FF8C42")       # оранжевый — и закрытия, и сезонность
_COLOR_INACTIVE = QColor("#AAAAAA")      # серый — неактивная запись


def _make_badge_item(text: str, bg: QColor | None = None) -> QTableWidgetItem:
    """Создаёт ячейку с цветным фоном для индикатора."""
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if bg:
        item.setBackground(bg)
        # Подбираем контрастный цвет текста
        luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        item.setForeground(
            QColor("white") if luminance < 140 else QColor("#222222")
        )
    return item


class OrgsVenuesPage(QWidget):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.user = user

        # =====================================================================
        # ---------- Левая часть: Учреждения
        # =====================================================================
        self.lbl_orgs = QLabel("Учреждения")
        self.lbl_orgs.setObjectName("sectionTitle")

        self.ed_org_search = QLineEdit()
        self.ed_org_search.setPlaceholderText("Поиск: имя / адрес")
        self.ed_org_search.setClearButtonEnabled(True)
        self.ed_org_search.returnPressed.connect(self.reload_orgs)

        self.cb_org_inactive = QCheckBox("Архив")
        self.cb_org_inactive.stateChanged.connect(lambda *_: self.reload_orgs())

        # --- Кнопки учреждений (строка 1: заголовок + поиск + чекбокс)
        org_row1 = QHBoxLayout()
        org_row1.setContentsMargins(0, 0, 0, 0)
        org_row1.setSpacing(8)
        org_row1.addWidget(self.lbl_orgs)
        org_row1.addWidget(self.ed_org_search, 1)
        org_row1.addWidget(self.cb_org_inactive)

        # --- Кнопки учреждений (строка 2: действия)
        self.btn_org_add     = QPushButton("➕ Создать")
        self.btn_org_edit    = QPushButton("✏️ Редактировать")
        self.btn_org_archive = QPushButton("🗄 Архив/Восстановить")
        self.btn_org_closures = QPushButton("🔒 Закрытия…")

        for b in (
            self.btn_org_add,
            self.btn_org_edit,
            self.btn_org_archive,
            self.btn_org_closures,
        ):
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_org_add.clicked.connect(self._org_add)
        self.btn_org_edit.clicked.connect(self._org_edit)
        self.btn_org_archive.clicked.connect(self._org_toggle)
        self.btn_org_closures.clicked.connect(self._org_closures)

        org_row2 = QHBoxLayout()
        org_row2.setContentsMargins(0, 0, 0, 0)
        org_row2.setSpacing(6)
        org_row2.addWidget(self.btn_org_add)
        org_row2.addWidget(self.btn_org_edit)
        org_row2.addWidget(self.btn_org_archive)
        org_row2.addWidget(self.btn_org_closures)
        org_row2.addStretch(1)   # прижимаем кнопки влево

        # Таблица учреждений: добавляем колонку "Закрытия"
        # Колонки: ID | Название | Адрес | Режим | Активен | Закрытия
        self.tbl_orgs = QTableWidget(0, 6)
        self.tbl_orgs.setObjectName("orgsTable")
        self.tbl_orgs.setHorizontalHeaderLabels(
            ["ID", "Название", "Адрес", "Режим", "Активен", "Закрытия"]
        )
        self._style_table(self.tbl_orgs)
        self.tbl_orgs.itemSelectionChanged.connect(self._on_org_selected)
        self.tbl_orgs.doubleClicked.connect(self._org_edit)

        # Легенда для таблицы учреждений
        org_legend = self._make_legend([
            (_COLOR_CLOSURE, "Есть закрытия"),
        ])

        orgs_card = QWidget(self)
        orgs_card.setObjectName("detailsCard")
        orgs_card_lay = QVBoxLayout(orgs_card)
        orgs_card_lay.setContentsMargins(10, 10, 10, 6)
        orgs_card_lay.setSpacing(4)
        orgs_card_lay.addWidget(self.tbl_orgs)
        orgs_card_lay.addLayout(org_legend)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        left.addLayout(org_row1)
        left.addLayout(org_row2)
        left.addWidget(orgs_card, 1)

        # =====================================================================
        # ---------- Правая часть: Площадки
        # =====================================================================
        self.lbl_venues = QLabel("Площадки: (выберите учреждение слева)")
        self.lbl_venues.setObjectName("sectionTitle")

        self.cb_venue_inactive = QCheckBox("Архив")
        self.cb_venue_inactive.stateChanged.connect(lambda *_: self.reload_venues())

        # --- Кнопки площадок (строка 1: заголовок + чекбокс)
        venue_row1 = QHBoxLayout()
        venue_row1.setContentsMargins(0, 0, 0, 0)
        venue_row1.setSpacing(8)
        venue_row1.addWidget(self.lbl_venues, 1)
        venue_row1.addWidget(self.cb_venue_inactive)

        # --- Кнопки площадок (строка 2: действия)
        self.btn_venue_add      = QPushButton("➕ Создать")
        self.btn_venue_edit     = QPushButton("✏️ Редактировать")
        self.btn_venue_archive  = QPushButton("🗄 Архив/Восстановить")
        self.btn_venue_closures = QPushButton("🔒 Закрытия…")
        self.btn_venue_seasons  = QPushButton("🗓 Сезонность…")

        for b in (
            self.btn_venue_add,
            self.btn_venue_edit,
            self.btn_venue_archive,
            self.btn_venue_closures,
            self.btn_venue_seasons,
        ):
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_venue_add.clicked.connect(self._venue_add)
        self.btn_venue_edit.clicked.connect(self._venue_edit)
        self.btn_venue_archive.clicked.connect(self._venue_toggle)
        self.btn_venue_closures.clicked.connect(self._venue_closures)
        self.btn_venue_seasons.clicked.connect(self._venue_seasons)

        venue_row2 = QHBoxLayout()
        venue_row2.setContentsMargins(0, 0, 0, 0)
        venue_row2.setSpacing(6)
        venue_row2.addWidget(self.btn_venue_add)
        venue_row2.addWidget(self.btn_venue_edit)
        venue_row2.addWidget(self.btn_venue_archive)
        venue_row2.addWidget(self.btn_venue_closures)
        venue_row2.addWidget(self.btn_venue_seasons)
        venue_row2.addStretch(1)  # прижимаем кнопки влево

        # Таблица площадок: добавляем колонки "Закрытия" и "Сезонность"
        # Колонки: ID | Название | Тип спорта | Вместимость | Активен | Закрытия | Сезонность | Комментарий
        self.tbl_venues = QTableWidget(0, 8)
        self.tbl_venues.setObjectName("venuesTable")
        self.tbl_venues.setHorizontalHeaderLabels([
            "ID", "Название", "Тип спорта", "Вместимость",
            "Активен", "Закрытия", "Сезонность", "Комментарий",
        ])
        self._style_table(self.tbl_venues)
        self.tbl_venues.doubleClicked.connect(self._venue_edit)

        # Легенда для таблицы площадок
        venue_legend = self._make_legend([
            (_COLOR_CLOSURE, "Есть закрытия"),
            (_COLOR_SEASON,  "Есть сезонность"),
            (_COLOR_BOTH,    "Закрытия + сезонность"),
        ])

        venues_card = QWidget(self)
        venues_card.setObjectName("detailsCard")
        venues_card_lay = QVBoxLayout(venues_card)
        venues_card_lay.setContentsMargins(10, 10, 10, 6)
        venues_card_lay.setSpacing(4)
        venues_card_lay.addWidget(self.tbl_venues)
        venues_card_lay.addLayout(venue_legend)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        right.addLayout(venue_row1)
        right.addLayout(venue_row2)
        right.addWidget(venues_card, 1)

        # =====================================================================
        # ---------- Корневой layout
        # =====================================================================
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(12)
        root.addLayout(left, 1)
        root.addLayout(right, 1)

        self.reload_orgs()

    # =========================================================================
    # Вспомогательные методы
    # =========================================================================

    def _make_legend(self, items: list[tuple[QColor, str]]) -> QHBoxLayout:
        """Создаёт горизонтальную легенду с цветными патчами."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(12)
        layout.addStretch(1)

        for color, text in items:
            patch = QLabel("  ")
            patch.setFixedSize(18, 14)
            patch.setStyleSheet(
                f"background-color: {color.name()}; "
                f"border-radius: 3px; border: 1px solid #ccc;"
            )
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 11px; color: #555;")

            layout.addWidget(patch)
            layout.addWidget(lbl)

        return layout

    def _is_admin(self) -> bool:
        return (self.user.role_code or "").lower() == "admin"

    def _org_access(self, org_id: int):
        return get_org_access(
            user_id=self.user.id,
            role_code=self.user.role_code,
            org_id=org_id,
        )

    def _apply_ui_access(self):
        org = self._selected_org()
        self.btn_org_add.setEnabled(self._is_admin())

        if not org:
            for b in (
                self.btn_org_edit, self.btn_org_archive,
                self.btn_venue_add, self.btn_venue_edit,
                self.btn_venue_archive, self.btn_org_closures,
                self.btn_venue_closures, self.btn_venue_seasons,
            ):
                b.setEnabled(False)
            return

        acc = self._org_access(org.id)
        self.btn_org_edit.setEnabled(acc.can_edit)
        self.btn_org_archive.setEnabled(acc.can_edit)
        self.btn_venue_add.setEnabled(acc.can_edit)
        self.btn_venue_edit.setEnabled(acc.can_edit)
        self.btn_venue_archive.setEnabled(acc.can_edit)
        self.btn_org_closures.setEnabled(acc.can_edit)
        self.btn_venue_closures.setEnabled(acc.can_edit)
        self.btn_venue_seasons.setEnabled(acc.can_edit)

    def _on_org_selected(self):
        self._apply_ui_access()
        self.reload_venues()

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
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setHighlightSections(False)

        f = QFont()
        f.setPointSize(max(f.pointSize(), 10))
        tbl.setFont(f)

        for c in range(tbl.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        # Последнюю колонку растягиваем
        header.setSectionResizeMode(
            tbl.columnCount() - 1, QHeaderView.ResizeMode.Stretch
        )

    # =========================================================================
    # Помощники выбора строк
    # =========================================================================

    def _selected_org(self) -> SportOrg | None:
        row = self.tbl_orgs.currentRow()
        if row < 0:
            return None
        item = self.tbl_orgs.item(row, 0)
        if not item:
            return None
        obj = item.data(Qt.ItemDataRole.UserRole)
        return obj if isinstance(obj, SportOrg) else None

    def _selected_venue(self) -> Venue | None:
        row = self.tbl_venues.currentRow()
        if row < 0:
            return None
        item = self.tbl_venues.item(row, 0)
        if not item:
            return None
        obj = item.data(Qt.ItemDataRole.UserRole)
        return obj if isinstance(obj, Venue) else None

    def _org_work_str(self, o: SportOrg) -> str:
        if getattr(o, "is_24h", False):
            return "24/7"
        ws = getattr(o, "work_start", None)
        we = getattr(o, "work_end", None)
        if ws and we:
            return f"{ws:%H:%M}–{we:%H:%M}"
        return "—"

    # =========================================================================
    # Перезагрузка данных
    # =========================================================================

    def reload_orgs(self):
        selected = self._selected_org()
        selected_id = selected.id if selected else None

        try:
            orgs = list_orgs(
                user_id=self.user.id,
                role_code=self.user.role_code,
                search=self.ed_org_search.text(),
                include_inactive=self.cb_org_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Учреждения", f"Ошибка загрузки:\n{e}")
            return

        # Пакетный запрос статусов закрытий учреждений
        org_ids = [o.id for o in orgs]
        try:
            org_closure_statuses = get_org_closure_statuses(org_ids)
        except Exception:
            org_closure_statuses = {}   # не критично — просто не покажем метки

        self.tbl_orgs.setSortingEnabled(False)
        self.tbl_orgs.setRowCount(0)

        for o in orgs:
            r = self.tbl_orgs.rowCount()
            self.tbl_orgs.insertRow(r)

            it_id = QTableWidgetItem(str(o.id))
            it_id.setData(Qt.ItemDataRole.UserRole, o)
            it_id.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            it_work = QTableWidgetItem(self._org_work_str(o))
            it_work.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_active = QTableWidgetItem("Да" if o.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Индикатор закрытий учреждения
            has_cl = org_closure_statuses.get(o.id, False)
            it_closures = _make_badge_item(
                "🔒 Есть" if has_cl else "—",
                _COLOR_CLOSURE if has_cl else None,
            )

            self.tbl_orgs.setItem(r, 0, it_id)
            self.tbl_orgs.setItem(r, 1, QTableWidgetItem(o.name))
            self.tbl_orgs.setItem(r, 2, QTableWidgetItem(o.address or ""))
            self.tbl_orgs.setItem(r, 3, it_work)
            self.tbl_orgs.setItem(r, 4, it_active)
            self.tbl_orgs.setItem(r, 5, it_closures)

            # Затемняем неактивные строки
            if not o.is_active:
                for c in range(self.tbl_orgs.columnCount()):
                    it = self.tbl_orgs.item(r, c)
                    if it:
                        it.setForeground(_COLOR_INACTIVE)

        self.tbl_orgs.setSortingEnabled(True)

        if selected_id is not None:
            self._select_org_row_by_id(selected_id)

        self._apply_ui_access()
        self.reload_venues()

    def reload_venues(self):
        org = self._selected_org()
        if not org:
            self.lbl_venues.setText("Площадки: (выберите учреждение слева)")
            self.tbl_venues.setRowCount(0)
            return

        self.lbl_venues.setText(f"Площадки: {org.name}")

        selected = self._selected_venue()
        selected_id = selected.id if selected else None

        try:
            venues = list_venues(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                include_inactive=self.cb_venue_inactive.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Площадки", f"Ошибка загрузки:\n{e}")
            return

        # Пакетный запрос статусов площадок (закрытия + сезонность)
        venue_ids = [v.id for v in venues]
        try:
            venue_statuses = get_venue_statuses(venue_ids)
        except Exception:
            venue_statuses = {}   # не критично

        self.tbl_venues.setSortingEnabled(False)
        self.tbl_venues.setRowCount(0)

        for v in venues:
            r = self.tbl_venues.rowCount()
            self.tbl_venues.insertRow(r)

            it_id = QTableWidgetItem(str(v.id))
            it_id.setData(Qt.ItemDataRole.UserRole, v)
            it_id.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            it_cap = QTableWidgetItem(
                "" if v.capacity is None else str(v.capacity)
            )
            it_cap.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            it_active = QTableWidgetItem("Да" if v.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Индикаторы закрытий и сезонности
            st = venue_statuses.get(v.id, {})
            has_cl  = st.get("has_closures", False)
            has_sea = st.get("has_seasons",  False)

            # Выбираем цвет в зависимости от комбинации
            if has_cl and has_sea:
                cl_color  = _COLOR_BOTH
                sea_color = _COLOR_BOTH
            else:
                cl_color  = _COLOR_CLOSURE if has_cl  else None
                sea_color = _COLOR_SEASON  if has_sea else None

            it_closures = _make_badge_item(
                "🔒 Есть" if has_cl else "—", cl_color
            )
            it_seasons = _make_badge_item(
                "🗓 Есть" if has_sea else "—", sea_color
            )

            self.tbl_venues.setItem(r, 0, it_id)
            self.tbl_venues.setItem(r, 1, QTableWidgetItem(v.name))
            self.tbl_venues.setItem(r, 2, QTableWidgetItem(v.sport_type or ""))
            self.tbl_venues.setItem(r, 3, it_cap)
            self.tbl_venues.setItem(r, 4, it_active)
            self.tbl_venues.setItem(r, 5, it_closures)
            self.tbl_venues.setItem(r, 6, it_seasons)
            self.tbl_venues.setItem(r, 7, QTableWidgetItem(v.comment or ""))

            # Затемняем неактивные строки
            if not v.is_active:
                for c in range(self.tbl_venues.columnCount()):
                    it = self.tbl_venues.item(r, c)
                    if it:
                        it.setForeground(_COLOR_INACTIVE)

        self.tbl_venues.setSortingEnabled(True)

        if selected_id is not None:
            self._select_venue_row_by_id(selected_id)

        self._apply_ui_access()

    # =========================================================================
    # Действия с учреждениями
    # =========================================================================

    def _org_add(self):
        if not self._is_admin():
            QMessageBox.warning(
                self, "Доступ запрещён",
                "Создание учреждения доступно только администратору.",
            )
            return

        dlg = OrgDialog(self, title="Создать учреждение")
        if dlg.exec() != OrgDialog.Accepted:
            return

        data = dlg.values()
        try:
            new_id = create_org(
                user_id=self.user.id,
                role_code=self.user.role_code,
                name=data["name"],
                address=data["address"],
                comment=data["comment"],
                work_start=data["work_start"],
                work_end=data["work_end"],
                is_24h=data["is_24h"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Создать учреждение", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Учреждения", f"Создано учреждение (id={new_id}).")
        self.reload_orgs()
        self._select_org_row_by_id(new_id)

    def _org_edit(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Редактировать", "Выберите учреждение.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на редактирование этого учреждения.",
            )
            return

        dlg = OrgDialog(
            self,
            title=f"Редактировать: {org.name}",
            data={
                "name":       org.name,
                "address":    org.address,
                "comment":    org.comment,
                "work_start": getattr(org, "work_start", None),
                "work_end":   getattr(org, "work_end",   None),
                "is_24h":     getattr(org, "is_24h",     False),
            },
        )
        if dlg.exec() != OrgDialog.Accepted:
            return

        data = dlg.values()
        try:
            update_org(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                name=data["name"],
                address=data["address"],
                comment=data["comment"],
                work_start=data["work_start"],
                work_end=data["work_end"],
                is_24h=data["is_24h"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Редактировать учреждение", f"Ошибка:\n{e}")
            return

        self.reload_orgs()
        self._select_org_row_by_id(org.id)

    def _org_toggle(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Архив", "Выберите учреждение.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на изменение статуса этого учреждения.",
            )
            return

        new_state = not org.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self, "Подтверждение",
                f"Вы действительно хотите {action} учреждение «{org.name}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_org_active(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                is_active=new_state,
            )
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload_orgs()

    # =========================================================================
    # Действия с площадками
    # =========================================================================

    def _venue_add(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Площадки", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на редактирование площадок этого учреждения.",
            )
            return

        dlg = VenueDialog(self, title=f"Создать площадку — {org.name}")
        if dlg.exec() != VenueDialog.Accepted:
            return

        data = dlg.values()
        try:
            new_id = create_venue(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                name=data["name"],
                sport_type=data["sport_type"],
                capacity=data["capacity"],
                comment=data["comment"],
            )
            apply_units_scheme(new_id, data["units_scheme"])
        except Exception as e:
            QMessageBox.critical(self, "Создать площадку", f"Ошибка:\n{e}")
            return

        QMessageBox.information(self, "Площадки", f"Создана площадка (id={new_id}).")
        self.reload_venues()
        self._select_venue_row_by_id(new_id)

    def _venue_edit(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Редактировать", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на редактирование площадок этого учреждения.",
            )
            return

        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Редактировать", "Выберите площадку.")
            return

        dlg = VenueDialog(
            self,
            title=f"Редактировать площадку: {v.name}",
            data={
                "id":         v.id,
                "name":       v.name,
                "sport_type": v.sport_type,
                "capacity":   v.capacity,
                "comment":    v.comment,
            },
        )
        if dlg.exec() != VenueDialog.Accepted:
            return

        data = dlg.values()
        try:
            update_venue(
                user_id=self.user.id,
                role_code=self.user.role_code,
                venue_id=v.id,
                name=data["name"],
                sport_type=data["sport_type"],
                capacity=data["capacity"],
                comment=data["comment"],
            )
            apply_units_scheme(v.id, data["units_scheme"])
        except Exception as e:
            QMessageBox.critical(self, "Редактировать площадку", f"Ошибка:\n{e}")
            return

        self.reload_venues()
        self._select_venue_row_by_id(v.id)

    def _venue_toggle(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Архив", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на изменение статуса площадок этого учреждения.",
            )
            return

        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Архив", "Выберите площадку.")
            return

        new_state = not v.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(
                self, "Подтверждение",
                f"Вы действительно хотите {action} площадку «{v.name}»?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_venue_active(
                user_id=self.user.id,
                role_code=self.user.role_code,
                venue_id=v.id,
                is_active=new_state,
            )
        except Exception as e:
            QMessageBox.critical(self, "Архив", f"Ошибка:\n{e}")
            return

        self.reload_venues()

    # =========================================================================
    # Выбор строк по ID
    # =========================================================================

    def _select_org_row_by_id(self, org_id: int) -> None:
        for r in range(self.tbl_orgs.rowCount()):
            item = self.tbl_orgs.item(r, 0)
            if item and item.text() == str(org_id):
                self.tbl_orgs.setCurrentCell(r, 0)
                self.tbl_orgs.scrollToItem(item)
                return

    def _select_venue_row_by_id(self, venue_id: int) -> None:
        for r in range(self.tbl_venues.rowCount()):
            item = self.tbl_venues.item(r, 0)
            if item and item.text() == str(venue_id):
                self.tbl_venues.setCurrentCell(r, 0)
                self.tbl_venues.scrollToItem(item)
                return

    # =========================================================================
    # Диалоги закрытий и сезонности
    # =========================================================================

    def _org_closures(self):
        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Закрытия", "Выберите учреждение.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на редактирование этого учреждения.",
            )
            return

        dlg = ClosuresManageDialog(
            self,
            title=f"Закрытия учреждения — {org.name}",
            list_fn=lambda include_inactive=False: list_org_closures(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                include_inactive=include_inactive,
            ),
            create_fn=lambda date_from, date_to, reason: create_org_closure(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                date_from=date_from,
                date_to=date_to,
                reason=reason,
            ),
            update_fn=lambda closure_id, date_from, date_to, reason, is_active: update_org_closure(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                closure_id=closure_id,
                date_from=date_from,
                date_to=date_to,
                reason=reason,
                is_active=is_active,
            ),
            set_active_fn=lambda closure_id, is_active: set_org_closure_active(
                user_id=self.user.id,
                role_code=self.user.role_code,
                org_id=org.id,
                closure_id=closure_id,
                is_active=is_active,
            ),
        )
        dlg.exec()
        # Обновляем таблицу после закрытия диалога
        self.reload_orgs()

    def _venue_closures(self):
        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Закрытия", "Выберите площадку.")
            return

        org = self._selected_org()
        if not org:
            QMessageBox.information(self, "Закрытия", "Сначала выберите учреждение слева.")
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на редактирование площадок этого учреждения.",
            )
            return

        dlg = ClosuresManageDialog(
            self,
            title=f"Закрытия площадки — {v.name}",
            list_fn=lambda include_inactive=False: list_venue_closures(
                user_id=self.user.id,
                role_code=self.user.role_code,
                venue_id=v.id,
                include_inactive=include_inactive,
            ),
            create_fn=lambda date_from, date_to, reason: create_venue_closure(
                user_id=self.user.id,
                role_code=self.user.role_code,
                venue_id=v.id,
                date_from=date_from,
                date_to=date_to,
                reason=reason,
            ),
            update_fn=lambda closure_id, date_from, date_to, reason, is_active: update_venue_closure(
                user_id=self.user.id,
                role_code=self.user.role_code,
                venue_id=v.id,
                closure_id=closure_id,
                date_from=date_from,
                date_to=date_to,
                reason=reason,
                is_active=is_active,
            ),
            set_active_fn=lambda closure_id, is_active: set_venue_closure_active(
                user_id=self.user.id,
                role_code=self.user.role_code,
                venue_id=v.id,
                closure_id=closure_id,
                is_active=is_active,
            ),
        )
        dlg.exec()
        # Обновляем таблицу после закрытия диалога
        self.reload_venues()

    def _venue_seasons(self):
        v = self._selected_venue()
        if not v:
            QMessageBox.information(self, "Сезонность", "Выберите площадку.")
            return

        org = self._selected_org()
        if not org:
            QMessageBox.information(
                self, "Сезонность", "Сначала выберите учреждение слева."
            )
            return

        acc = self._org_access(org.id)
        if not acc.can_edit:
            QMessageBox.warning(
                self, "Доступ запрещён",
                "У вас нет прав на редактирование площадок этого учреждения.",
            )
            return

        dlg = VenueSeasonsManageDialog(
            self,
            user_id=self.user.id,
            role_code=self.user.role_code,
            venue_id=v.id,
        )
        dlg.exec()
        # Обновляем таблицу после закрытия диалога
        self.reload_venues()
