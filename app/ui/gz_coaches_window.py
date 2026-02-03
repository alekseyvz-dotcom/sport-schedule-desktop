# app/ui/gz_coaches_window.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QCheckBox,
    QAbstractItemView,
    QHeaderView,
    QComboBox,
)

from app.services.users_service import AuthUser
from app.services.access_service import list_allowed_org_ids
from app.services.ref_service import list_active_orgs_by_ids

from app.services.gz_service import (
    GzCoach,
    list_coaches,
    create_coach,
    update_coach,
    set_coach_active,
    get_coach_org_ids,
    set_coach_orgs,
    list_coach_orgs_map,  # важно: функция должна быть обновлена и принимать org_ids=
)
from app.ui.gz_coach_dialog import GzCoachDialog


class GzCoachesWindow(QDialog):
    def __init__(self, user: AuthUser, parent=None):
        super().__init__(parent)
        self.user = user

        self.setWindowTitle("Тренеры (ГЗ)")
        self.resize(860, 560)

        self._orgs: list[dict] = []  # [{id, name}] только разрешённые пользователю

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск тренера…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.returnPressed.connect(self.reload)

        self.cmb_org = QComboBox()
        self.cmb_org.addItem("Все объекты", None)
        self.cmb_org.currentIndexChanged.connect(lambda *_: self.reload())

        self.cb_inactive = QCheckBox("Архив")
        self.cb_inactive.stateChanged.connect(lambda *_: self.reload())

        self.btn_add = QPushButton("Создать")
        self.btn_edit = QPushButton("Редактировать")
        self.btn_archive = QPushButton("Архивировать/восстановить")
        self.btn_close = QPushButton("Закрыть")

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_archive.clicked.connect(self._on_toggle_active)
        self.btn_close.clicked.connect(self.accept)

        top = QHBoxLayout()
        top.addWidget(self.ed_search, 1)
        top.addWidget(self.cmb_org)
        top.addWidget(self.cb_inactive)
        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_archive)

        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["ID", "ФИО", "Объекты", "Комментарий", "Активен"])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.doubleClicked.connect(lambda *_: self._on_edit())

        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.btn_close)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.tbl, 1)
        root.addLayout(bottom)

        self._load_orgs()
        self.reload()

    def _allowed_org_ids_list(self) -> list[int]:
        return [int(o["id"]) for o in (self._orgs or [])]

    def _allowed_org_ids_set(self) -> set[int]:
        return {int(o["id"]) for o in (self._orgs or [])}

    def _load_orgs(self):
        try:
            allowed_ids = list_allowed_org_ids(int(self.user.id), str(self.user.role_code))
            orgs = list_active_orgs_by_ids(allowed_ids)

            self._orgs = [{"id": int(o.id), "name": str(o.name)} for o in orgs]

            self.cmb_org.blockSignals(True)
            self.cmb_org.clear()
            self.cmb_org.addItem("Все объекты", None)
            for o in self._orgs:
                self.cmb_org.addItem(o["name"], o["id"])
            self.cmb_org.blockSignals(False)

        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Ошибка загрузки учреждений:\n{e}")
            self._orgs = []

    def _selected(self) -> GzCoach | None:
        row = self.tbl.currentRow()
        if row < 0:
            return None
        it = self.tbl.item(row, 0)
        obj = it.data(Qt.ItemDataRole.UserRole) if it else None
        return obj if isinstance(obj, GzCoach) else None

    def reload(self):
        org_id = self.cmb_org.currentData()
        org_id = int(org_id) if org_id is not None else None

        allowed_org_ids_list = self._allowed_org_ids_list()
        allowed_org_ids_set = self._allowed_org_ids_set()

        # если в комбобоксе каким-то образом оказался "чужой" org_id
        if org_id is not None and org_id not in allowed_org_ids_set:
            self.tbl.setRowCount(0)
            return

        try:
            rows = list_coaches(
                search=self.ed_search.text(),
                include_inactive=self.cb_inactive.isChecked(),
                org_id=org_id,
                org_ids=allowed_org_ids_list,
                user_id=self.user.id,
                role_code=self.user.role_code,
            )

            coach_orgs = list_coach_orgs_map(
                include_inactive_orgs=False,
                org_ids=allowed_org_ids_list,
            )
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Ошибка загрузки:\n{e}")
            return

        self.tbl.setRowCount(0)
        for c in rows:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            orgs_str = ", ".join(coach_orgs.get(int(c.id), [])) or "—"

            it_id = QTableWidgetItem(str(c.id))
            it_id.setData(Qt.ItemDataRole.UserRole, c)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            it_active = QTableWidgetItem("Да" if c.is_active else "Нет")
            it_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl.setItem(r, 0, it_id)
            self.tbl.setItem(r, 1, QTableWidgetItem(c.full_name))
            self.tbl.setItem(r, 2, QTableWidgetItem(orgs_str))
            self.tbl.setItem(r, 3, QTableWidgetItem(c.comment or ""))
            self.tbl.setItem(r, 4, it_active)

            if not c.is_active:
                for col in range(self.tbl.columnCount()):
                    it = self.tbl.item(r, col)
                    if it:
                        it.setForeground(Qt.GlobalColor.darkGray)

    def _on_add(self):
        if not self._orgs:
            QMessageBox.warning(self, "Тренеры", "Нет доступных учреждений. Невозможно создать тренера.")
            return

        dlg = GzCoachDialog(self, "Создать тренера", orgs=self._orgs, selected_org_ids=[])
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        v = dlg.values()

        # защита от подмены/ошибки: сохраняем только разрешённые org_ids
        allowed = self._allowed_org_ids_set()
        org_ids = [int(x) for x in (v.get("org_ids") or []) if int(x) in allowed]

        try:
            new_id = create_coach(
                user_id=int(self.user.id),
                role_code=str(self.user.role_code),
                full_name=v["full_name"],
                comment=v.get("comment", ""),
            )
            set_coach_orgs(
                user_id=int(self.user.id),
                role_code=str(self.user.role_code),
                coach_id=int(new_id),
                org_ids=org_ids,
            )
        except Exception as e:
            QMessageBox.critical(self, "Создать тренера", str(e))
            return

        self.reload()

    def _on_edit(self):
        c = self._selected()
        if not c:
            QMessageBox.information(self, "Тренеры", "Выберите тренера.")
            return
        if not self._orgs:
            QMessageBox.warning(self, "Тренеры", "Нет доступных учреждений. Невозможно редактировать тренера.")
            return

        allowed = self._allowed_org_ids_set()

        try:
            selected_org_ids = get_coach_org_ids(
                user_id=int(self.user.id),
                role_code=str(self.user.role_code),
                coach_id=int(c.id),
            )
            selected_org_ids = [int(oid) for oid in selected_org_ids if int(oid) in allowed]
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", f"Не удалось загрузить объекты тренера:\n{e}")
            return

        dlg = GzCoachDialog(
            self,
            "Редактировать тренера",
            data={"full_name": c.full_name, "comment": c.comment},
            orgs=self._orgs,
            selected_org_ids=selected_org_ids,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        v = dlg.values()
        org_ids = [int(x) for x in (v.get("org_ids") or []) if int(x) in allowed]

        try:
            update_coach(
                user_id=int(self.user.id),
                role_code=str(self.user.role_code),
                coach_id=int(c.id),
                full_name=v["full_name"],
                comment=v.get("comment", ""),
            )
            set_coach_orgs(
                user_id=int(self.user.id),
                role_code=str(self.user.role_code),
                coach_id=int(c.id),
                org_ids=org_ids,
            )
        except Exception as e:
            QMessageBox.critical(self, "Редактировать тренера", str(e))
            return

        self.reload()

    def _on_toggle_active(self):
        c = self._selected()
        if not c:
            QMessageBox.information(self, "Тренеры", "Выберите тренера.")
            return

        new_state = not c.is_active
        action = "восстановить" if new_state else "архивировать"
        if (
            QMessageBox.question(self, "Подтверждение", f"Вы действительно хотите {action} «{c.full_name}»?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            set_coach_active(
                user_id=int(self.user.id),
                role_code=str(self.user.role_code),
                coach_id=int(c.id),
                is_active=new_state,
            )
        except Exception as e:
            QMessageBox.critical(self, "Тренеры", str(e))
            return

        self.reload()
