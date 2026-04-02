from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QTimeEdit,
    QMessageBox,
    QLabel,
)

from app.core.day_parts_settings import DayPartsSettings
from app.services.day_parts_settings_service import get_default_day_parts_settings


class DayPartsSettingsDialog(QDialog):
    def __init__(self, settings: DayPartsSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Интервалы утро / день / вечер")
        self.setModal(True)
        self.resize(360, 220)

        self.lbl_info = QLabel("Настройте интервалы времени для аналитики загрузки.")

        self.ed_morning_start = QTimeEdit()
        self.ed_morning_end = QTimeEdit()
        self.ed_day_start = QTimeEdit()
        self.ed_day_end = QTimeEdit()
        self.ed_evening_start = QTimeEdit()
        self.ed_evening_end = QTimeEdit()

        for w in (
            self.ed_morning_start,
            self.ed_morning_end,
            self.ed_day_start,
            self.ed_day_end,
            self.ed_evening_start,
            self.ed_evening_end,
        ):
            w.setDisplayFormat("HH:mm")
            w.setKeyboardTracking(False)

        self._apply_settings(settings)

        form = QFormLayout()
        form.addRow("Утро: с", self.ed_morning_start)
        form.addRow("Утро: по", self.ed_morning_end)
        form.addRow("День: с", self.ed_day_start)
        form.addRow("День: по", self.ed_day_end)
        form.addRow("Вечер: с", self.ed_evening_start)
        form.addRow("Вечер: по", self.ed_evening_end)

        self.btn_defaults = QPushButton("По умолчанию")
        self.btn_ok = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")

        self.btn_defaults.clicked.connect(self._reset_defaults)
        self.btn_ok.clicked.connect(self._accept_validated)
        self.btn_cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_defaults)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_ok)
        buttons.addWidget(self.btn_cancel)

        root = QVBoxLayout(self)
        root.addWidget(self.lbl_info)
        root.addLayout(form)
        root.addStretch(1)
        root.addLayout(buttons)

    def _apply_settings(self, settings: DayPartsSettings) -> None:
        self.ed_morning_start.setTime(QTime.fromString(settings.morning_start, "HH:mm"))
        self.ed_morning_end.setTime(QTime.fromString(settings.morning_end, "HH:mm"))
        self.ed_day_start.setTime(QTime.fromString(settings.day_start, "HH:mm"))
        self.ed_day_end.setTime(QTime.fromString(settings.day_end, "HH:mm"))
        self.ed_evening_start.setTime(QTime.fromString(settings.evening_start, "HH:mm"))
        self.ed_evening_end.setTime(QTime.fromString(settings.evening_end, "HH:mm"))

    def _reset_defaults(self) -> None:
        self._apply_settings(get_default_day_parts_settings())

    def _accept_validated(self) -> None:
        ms = self.ed_morning_start.time()
        me = self.ed_morning_end.time()
        ds = self.ed_day_start.time()
        de = self.ed_day_end.time()
        es = self.ed_evening_start.time()
        ee = self.ed_evening_end.time()

        if not (ms < me):
            QMessageBox.warning(self, "Проверка", "Для интервала 'Утро' начало должно быть меньше окончания.")
            return
        if not (ds < de):
            QMessageBox.warning(self, "Проверка", "Для интервала 'День' начало должно быть меньше окончания.")
            return
        if not (es < ee):
            QMessageBox.warning(self, "Проверка", "Для интервала 'Вечер' начало должно быть меньше окончания.")
            return
        if me > ds:
            QMessageBox.warning(self, "Проверка", "Интервалы 'Утро' и 'День' не должны пересекаться.")
            return
        if de > es:
            QMessageBox.warning(self, "Проверка", "Интервалы 'День' и 'Вечер' не должны пересекаться.")
            return

        self.accept()

    def get_settings(self) -> DayPartsSettings:
        return DayPartsSettings(
            morning_start=self.ed_morning_start.time().toString("HH:mm"),
            morning_end=self.ed_morning_end.time().toString("HH:mm"),
            day_start=self.ed_day_start.time().toString("HH:mm"),
            day_end=self.ed_day_end.time().toString("HH:mm"),
            evening_start=self.ed_evening_start.time().toString("HH:mm"),
            evening_end=self.ed_evening_end.time().toString("HH:mm"),
        )
