# app/ui/fit_screen.py
"""
Подгонка окон под экран ноутбука.

Проблема: диалоги задают размеры вроде `resize(980, 640)`, но их
содержимое требует больше — например, карточка контрагента просит
минимум 1083x768. На ноутбуке 1366x768 доступно ~728 px по высоте,
поэтому нижние кнопки уезжают за край экрана.

Два инструмента:

  fit_dialog_to_screen(dlg)
      Ограничивает размер окна доступной геометрией экрана.
      Вызывать последним в __init__.

  make_scrollable(dlg)
      Оборачивает содержимое в прокрутку, оставляя нижние кнопки
      закреплёнными. После этого диалог может быть меньше своего
      содержимого — ничего не пропадает.

Обе функции безопасны: если что-то не так, диалог просто останется
как был.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# Доля экрана, которую разрешено занимать окну
MAX_WIDTH_RATIO = 0.96
MAX_HEIGHT_RATIO = 0.92


def _screen_size(widget: QWidget) -> QSize:
    """Доступная область экрана, на котором находится виджет."""
    screen = None
    try:
        screen = widget.screen()
    except Exception:
        screen = None
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return QSize(1366, 728)
    return screen.availableGeometry().size()


def fit_dialog_to_screen(
    dlg: QDialog,
    *,
    width: int | None = None,
    height: int | None = None,
    max_width_ratio: float = MAX_WIDTH_RATIO,
    max_height_ratio: float = MAX_HEIGHT_RATIO,
) -> None:
    """
    Подгоняет размер диалога под экран.

    width/height — желаемый размер. Если не указаны, берётся текущий
    размер диалога. Итог всегда вписан в доступную область экрана.
    """
    avail = _screen_size(dlg)
    limit_w = max(320, int(avail.width() * max_width_ratio))
    limit_h = max(240, int(avail.height() * max_height_ratio))

    want_w = int(width if width is not None else dlg.width())
    want_h = int(height if height is not None else dlg.height())

    w = min(max(want_w, 320), limit_w)
    h = min(max(want_h, 240), limit_h)

    dlg.resize(w, h)


def _is_bottom_buttons(item) -> bool:
    """Последний элемент — контейнер с кнопками ОК/Отмена?"""
    widget = item.widget()
    if isinstance(widget, QDialogButtonBox):
        return True

    layout = item.layout()
    if isinstance(layout, QHBoxLayout):
        # строка только из кнопок и «распорок»
        has_button = False
        for i in range(layout.count()):
            sub = layout.itemAt(i)
            if sub is None:
                continue
            w = sub.widget()
            if isinstance(w, QPushButton):
                has_button = True
            elif w is not None:
                return False
            elif sub.spacerItem() is None:
                return False
        return has_button

    return False


def make_scrollable(
    dlg: QDialog,
    *,
    margins: tuple[int, int, int, int] | None = None,
) -> QScrollArea | None:
    """
    Оборачивает содержимое диалога в прокрутку.

    Нижняя строка с кнопками (QDialogButtonBox или QHBoxLayout из кнопок)
    остаётся закреплённой — она всегда видна, даже если содержимое
    не помещается.

    Возвращает QScrollArea или None, если обернуть не удалось.
    """
    old = dlg.layout()
    if old is None or old.count() == 0:
        return None

    # ── отделяем нижние кнопки, если они — последний элемент
    bottom = None
    last_index = old.count() - 1
    last_item = old.itemAt(last_index)
    if last_item is not None and _is_bottom_buttons(last_item):
        taken = old.takeAt(last_index)
        if isinstance(taken.widget(), QDialogButtonBox):
            bottom = taken.widget()
        elif taken.layout() is not None:
            bottom_host = QWidget()
            bottom_host.setLayout(taken.layout())
            bottom = bottom_host

    # ── переносим оставшийся layout на контейнер
    try:
        container = QWidget()
        container.setLayout(old)
    except Exception:
        # не получилось — возвращаем кнопки назад и выходим
        if bottom is not None:
            old.addWidget(bottom)
        return None

    scroll = QScrollArea(dlg)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(container)

    root = QVBoxLayout(dlg)
    if margins is None:
        margins = (0, 0, 0, 0)
    root.setContentsMargins(*margins)
    root.setSpacing(0)
    root.addWidget(scroll, 1)

    if bottom is not None:
        # небольшой отступ, чтобы кнопки не липли к содержимому
        wrap = QWidget(dlg)
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(12, 6, 12, 10)
        wrap_lay.setSpacing(0)
        wrap_lay.addWidget(bottom)
        root.addWidget(wrap, 0)

    # диалог больше не обязан быть размером с содержимое
    dlg.setMinimumSize(320, 240)

    return scroll


def fit_and_scroll(
    dlg: QDialog,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Удобная обёртка: прокрутка + подгонка под экран."""
    make_scrollable(dlg)
    fit_dialog_to_screen(dlg, width=width, height=height)
