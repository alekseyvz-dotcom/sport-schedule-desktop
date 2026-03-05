from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Set

from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QListView,
    QAbstractItemView,
    QDateEdit,
    QTimeEdit,
    QCheckBox,
)


def _make_scrollable_combo(cmb: QComboBox, *, max_visible: int = 14) -> None:
    view = QListView()
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    cmb.setView(view)
    cmb.setMaxVisibleItems(int(max_visible))


class BookingDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str = "Создать бронирование",
        starts_at: datetime,
        ends_at: datetime,
        venue_name: str,
        tenants: List[Dict],
        gz_groups: List[Dict],
        venue_units: Optional[List[Dict]] = None,
        initial: Optional[Dict] = None,
        selection_title: Optional[str] = None,
        selection_lines: Optional[List[str]] = None,
        allowed_kinds: Optional[Set[str]] = None,
        editable_time: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setObjectName("dialog")

        self._venue_units = venue_units or []
        self._tenants = tenants or []
        self._gz_groups = gz_groups or []
        self._editable_time = editable_time
        self._original_starts_at = starts_at
        self._original_ends_at = ends_at
        initial = initial or {}

        self._allowed_kinds = {k.upper() for k in (allowed_kinds or {"PD", "GZ"})} or {"PD", "GZ"}

        # ── Информационный лейбл (для создания — статический) ──
        self.lbl_info = QLabel(
            f"Площадка: <b>{venue_name}</b><br>"
            f"Время: <b>{starts_at:%d.%m.%Y %H:%M}</b> – <b>{ends_at:%H:%M}</b>"
        )
        self.lbl_info.setWordWrap(True)

        # ── Редактируемые поля даты/времени (для редактирования) ──
        self.dt_date = QDateEdit()
        self.dt_date.setCalendarPopup(True)
        self.dt_date.setDisplayFormat("dd.MM.yyyy")
        self.dt_date.setDate(QDate(starts_at.year, starts_at.month, starts_at.day))

        self.tm_start = QTimeEdit()
        self.tm_start.setDisplayFormat("HH:mm")
        self.tm_start.setTime(QTime(starts_at.hour, starts_at.minute))

        self.tm_end = QTimeEdit()
        self.tm_end.setDisplayFormat("HH:mm")
        self.tm_end.setTime(QTime(ends_at.hour, ends_at.minute))

        # ── Selection info ──
        self.lbl_selection = QLabel("")
        self.lbl_selection.setWordWrap(True)
        self.lbl_selection.setVisible(False)
        if selection_title or selection_lines:
            lines = selection_lines or []
            text = f"<b>{selection_title or ''}</b>"
            if lines:
                text += "<br>" + "<br>".join(f"• {s}" for s in lines)
            self.lbl_selection.setText(text)
            self.lbl_selection.setVisible(True)

        # ── Kind combo ──
        self.cmb_kind = QComboBox()
        if "PD" in self._allowed_kinds:
            self.cmb_kind.addItem("ПД (контрагент)", "PD")
        if "GZ" in self._allowed_kinds:
            self.cmb_kind.addItem("ГЗ (гос. задание)", "GZ")
        self.cmb_kind.setEnabled(self.cmb_kind.count() > 1)

        # ── Subject combo ──
        self.cmb_subject = QComboBox()
        _make_scrollable_combo(self.cmb_subject, max_visible=14)
        self.lbl_subject = QLabel("Контрагент:")

        # ── Unit combo ──
        self.cmb_unit = QComboBox()
        _make_scrollable_combo(self.cmb_unit, max_visible=12)
        if self._venue_units:
            for u in self._venue_units:
                self.cmb_unit.addItem(u["name"], u["id"])
        else:
            self.cmb_unit.addItem("—", None)
            self.cmb_unit.setEnabled(False)

        # ── Title ──
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Необязательно. Например: Тренировка / Секция / Аренда")

        self.cmb_kind.currentIndexChanged.connect(self._rebuild_subjects)

        # --- initial ---
        k = (initial.get("kind") or "PD").upper()
        i = self.cmb_kind.findData(k)
        self.cmb_kind.setCurrentIndex(i if i >= 0 else 0)

        self._rebuild_subjects()

        kind_now = (self.cmb_kind.currentData() or "PD").upper()
        if kind_now == "GZ":
            gid = initial.get("gz_group_id")
            if gid is not None:
                i = self.cmb_subject.findData(int(gid))
                if i >= 0:
                    self.cmb_subject.setCurrentIndex(i)
        else:
            tid = initial.get("tenant_id")
            if tid is not None:
                i = self.cmb_subject.findData(int(tid))
                if i >= 0:
                    self.cmb_subject.setCurrentIndex(i)

        unit_id = initial.get("venue_unit_id")
        if self._venue_units and unit_id is not None:
            i = self.cmb_unit.findData(int(unit_id))
            if i >= 0:
                self.cmb_unit.setCurrentIndex(i)

        self.ed_title.setText((initial.get("title") or "").strip())
        # --- end initial ---

        # ── Form layout ──
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        if self._editable_time:
            # Время редактируемое — показываем поля
            time_row = QHBoxLayout()
            time_row.setSpacing(8)
            time_row.addWidget(self.tm_start)
            time_row.addWidget(QLabel("–"))
            time_row.addWidget(self.tm_end)
            time_row.addStretch()

            form.addRow("Дата:", self.dt_date)
            form.addRow("Время:", time_row)

        form.addRow("Тип занятости:", self.cmb_kind)
        form.addRow(self.lbl_subject, self.cmb_subject)
        if self._venue_units:
            form.addRow("Зона:", self.cmb_unit)
        form.addRow("Название:", self.ed_title)

        # ── Buttons ──
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)

        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

        # ── Root layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        if self._editable_time:
            # В режиме редактирования — показываем venue_name как label без статичного времени
            lbl_venue = QLabel(f"Площадка: <b>{venue_name}</b>")
            lbl_venue.setWordWrap(True)
            root.addWidget(lbl_venue)
        else:
            root.addWidget(self.lbl_info)

        root.addWidget(self.lbl_selection)
        root.addLayout(form)
        root.addWidget(self.buttons)

    def _rebuild_subjects(self):
        kind = (self.cmb_kind.currentData() or "PD").upper()

        self.cmb_subject.blockSignals(True)
        self.cmb_subject.clear()

        if kind == "GZ":
            self.lbl_subject.setText("Гос. задание (группа):")
            for g in self._gz_groups:
                self.cmb_subject.addItem(g["name"], g["id"])
        else:
            self.lbl_subject.setText("Контрагент:")
            for t in self._tenants:
                self.cmb_subject.addItem(t["name"], t["id"])

        self.cmb_subject.blockSignals(False)

    def _on_accept(self):
        """Валидация перед accept."""
        if self._editable_time:
            q_start = self.tm_start.time()
            q_end = self.tm_end.time()
            if q_end <= q_start:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Ошибка",
                    "Время окончания должно быть позже времени начала.",
                )
                return
        self.accept()

    def values(self) -> Dict:
        unit_id = self.cmb_unit.currentData()
        kind = (self.cmb_kind.currentData() or "PD").upper()
        subject_id = self.cmb_subject.currentData()

        out = {
            "kind": kind,
            "venue_unit_id": (int(unit_id) if unit_id is not None else None),
            "title": self.ed_title.text().strip(),
        }

        if kind == "GZ":
            out["gz_group_id"] = int(subject_id) if subject_id is not None else None
            out["tenant_id"] = None
        else:
            out["tenant_id"] = int(subject_id) if subject_id is not None else None
            out["gz_group_id"] = None

        # Добавляем время если редактируемое
        if self._editable_time:
            q_date = self.dt_date.date().toPython()
            q_start = self.tm_start.time().toPython()
            q_end = self.tm_end.time().toPython()
            out["starts_at"] = datetime.combine(q_date, q_start)
            out["ends_at"] = datetime.combine(q_date, q_end)
            out["time_changed"] = (
                out["starts_at"] != self._original_starts_at.replace(tzinfo=None)
                or out["ends_at"] != self._original_ends_at.replace(tzinfo=None)
            )
        else:
            out["starts_at"] = None
            out["ends_at"] = None
            out["time_changed"] = False

        return out
