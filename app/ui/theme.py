# app/ui/theme.py

DARK_APP_QSS = """
/* ---- Base ---- */
QMainWindow {
    background: #0b1220;
    color: rgba(255, 255, 255, 0.88);
    font-size: 13px;
}
QWidget {
    color: rgba(255, 255, 255, 0.88);
    font-size: 13px;
    background: transparent;
}

/* ---- Unified page background ---- */
QWidget#page { background: #0b1220; }

/* ---- Tooltip ---- */
QToolTip {
    background: rgba(11, 18, 32, 0.98);
    color: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.14);
    padding: 6px 8px;
    border-radius: 8px;
}

/* ---- Status bar ---- */
QStatusBar {
    background: rgba(255, 255, 255, 0.04);
    border-top: 1px solid rgba(255, 255, 255, 0.10);
}
QStatusBar QLabel { color: rgba(226, 232, 240, 0.65); }

/* ---- Tabs ---- */
QTabWidget::pane {
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    top: -1px;
    background: rgba(15, 23, 42, 0.35);
}
QTabBar::tab {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(226, 232, 240, 0.80);
    border: 1px solid rgba(255, 255, 255, 0.10);
    padding: 8px 14px;
    margin-right: 6px;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QTabBar::tab:selected {
    background: rgba(15, 23, 42, 0.55);
    color: rgba(255, 255, 255, 0.92);
    border-color: rgba(99, 102, 241, 0.55);
}
QTabBar::tab:hover { border-color: rgba(255, 255, 255, 0.22); }

/* ---- Titles ---- */
QLabel#sectionTitle {
    color: rgba(255,255,255,0.92);
    font-weight: 900;
    font-size: 16px;
    padding-right: 8px;
}
QLabel#dlgTitle { color: rgba(255,255,255,0.92); font-weight: 900; font-size: 14px; }
QLabel#hint { color: rgba(226, 232, 240, 0.60); font-size: 12px; }

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit,
QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
QComboBox, QAbstractSpinBox {
    background: rgba(11, 18, 32, 0.65);
    color: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
    padding: 8px 10px;
    selection-background-color: rgba(99, 102, 241, 0.55);
}
QLineEdit::placeholder { color: rgba(226, 232, 240, 0.45); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QAbstractSpinBox:focus {
    border: 1px solid rgba(99, 102, 241, 0.95);
    background: rgba(11, 18, 32, 0.78);
}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    width: 18px;
    border: none;
    background: transparent;
}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
    background: rgba(255,255,255,0.06);
    border-radius: 6px;
}

/* ---- Buttons ---- */
QPushButton {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(226, 232, 240, 0.86);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
    padding: 8px 12px;
    font-weight: 700;
    min-height: 34px;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 0.10);
    border-color: rgba(255, 255, 255, 0.22);
}
QPushButton:pressed { background: rgba(255, 255, 255, 0.07); }
QPushButton:disabled {
    color: rgba(226, 232, 240, 0.35);
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.08);
}
/* “primary” */
QPushButton#primary {
    color: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(99, 102, 241, 0.75);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(99, 102, 241, 1.0),
        stop:1 rgba(34, 211, 238, 1.0)
    );
}
QPushButton#primary:hover { border-color: rgba(255, 255, 255, 0.22); }

/* ---- Checkbox ---- */
QCheckBox { spacing: 8px; color: rgba(226, 232, 240, 0.82); }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border-radius: 6px;
    background: rgba(11, 18, 32, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
QCheckBox::indicator:checked {
    background: rgba(99, 102, 241, 0.95);
    border-color: rgba(99, 102, 241, 0.95);
}

/* ---- Tables ---- */
QTableWidget, QTableView {
    background: rgba(15, 23, 42, 0.30);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 12px;
    gridline-color: transparent;
    alternate-background-color: rgba(255, 255, 255, 0.03);
    selection-background-color: rgba(99, 102, 241, 0.28);
    selection-color: rgba(255, 255, 255, 0.92);
}
QHeaderView::section {
    background: rgba(15, 23, 42, 0.55);
    color: rgba(226, 232, 240, 0.82);
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10);
    font-weight: 800;
}
QTableView::item { padding: 6px 10px; border: none; }
QTableView::item:selected { background: rgba(99, 102, 241, 0.28); }

/* ---- Scrollbar ---- */
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 6px 4px 6px 4px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.14);
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.22); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 4px 6px 4px 6px;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 0.14);
    border-radius: 6px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: rgba(255, 255, 255, 0.22); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

/* ---- Dialogs ---- */
QDialog, QDialog#dialog { background: #0b1220; }
QMessageBox { background: #0b1220; }
QMessageBox QLabel { color: rgba(226, 232, 240, 0.82); }

/* ---- GroupBox (cards) ---- */
QGroupBox {
    background: rgba(15, 23, 42, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    margin-top: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: rgba(255, 255, 255, 0.90);
    font-weight: 800;
    background: rgba(11, 18, 32, 0.98);
}

/* ---- DialogButtonBox ---- */
QDialogButtonBox { padding-top: 6px; }
QDialogButtonBox QPushButton { min-width: 120px; }

/* ---- ComboBox (arrow + popup) ---- */
QComboBox { padding-right: 28px; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid rgba(255, 255, 255, 0.12);
}
QComboBox::down-arrow {
    width: 12px;
    height: 12px;
    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2 4l4 4 4-4' fill='none' stroke='rgb(226,232,240)' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}
QComboBox QAbstractItemView {
    background: rgba(11, 18, 32, 0.98);
    color: rgba(255, 255, 255, 0.90);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
    selection-background-color: rgba(99, 102, 241, 0.35);
    outline: 0;
    padding: 6px;
}

/* ---- Calendar popup (QDateEdit) ---- */
QCalendarWidget QWidget { alternate-background-color: rgba(255, 255, 255, 0.04); }
QCalendarWidget QToolButton {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 10px;
    padding: 6px 10px;
}
QCalendarWidget QToolButton:hover {
    border-color: rgba(255, 255, 255, 0.22);
    background: rgba(255, 255, 255, 0.10);
}
QCalendarWidget QMenu {
    background: rgba(11, 18, 32, 0.98);
    color: rgba(255, 255, 255, 0.90);
    border: 1px solid rgba(255, 255, 255, 0.14);
}
QCalendarWidget QAbstractItemView:enabled {
    background: rgba(11, 18, 32, 0.92);
    color: rgba(255, 255, 255, 0.88);
    selection-background-color: rgba(99, 102, 241, 0.35);
    selection-color: rgba(255, 255, 255, 0.95);
    outline: 0;
}

/* ---- ScrollArea ---- */
QScrollArea { background: transparent; border: none; }

/* ---- View tabs (SchedulePage) ---- */
QToolButton#viewTab {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
    padding: 8px 12px;
    font-weight: 800;
    color: rgba(226, 232, 240, 0.82);
}
QToolButton#viewTab:hover {
    background: rgba(255, 255, 255, 0.10);
    border-color: rgba(255, 255, 255, 0.22);
}
QToolButton#viewTab:checked {
    background: rgba(15, 23, 42, 0.55);
    border-color: rgba(99, 102, 241, 0.65);
    color: rgba(255, 255, 255, 0.92);
}

/* ---- Details card ---- */
QWidget#detailsCard {
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 12px;
}
QLabel#detailsTitle {
    color: rgba(255, 255, 255, 0.92);
    font-weight: 900;
    padding: 10px 12px 0 12px;
}
QLabel#detailsText {
    color: rgba(226, 232, 240, 0.72);
    padding: 2px 12px;
}

/* ---- Meta labels / KPI ---- */
QLabel#scheduleMeta { color: rgba(226,232,240,0.65); padding: 0 4px; }
QLabel#scheduleMetaStrong { color: rgba(255,255,255,0.90); font-weight: 800; padding: 0 4px; }
QLabel#kpiTitle { color: rgba(226,232,240,0.60); }
QLabel#kpiValue { color: rgba(255,255,255,0.92); font-weight: 900; }

/* ---- Schedule tables: allow BackgroundRole (booking colors) ---- */
/* НЕ задаём background/color тут, чтобы работали BackgroundRole/ForegroundRole из кода */
QTableWidget#scheduleGrid::item { padding: 0px; }
QTableWidget#scheduleList::item { padding: 6px 10px; }
QTableWidget#scheduleGrid::item:selected,
QTableWidget#scheduleList::item:selected {
    outline: 1px solid rgba(99, 102, 241, 0.65);
}

/* ---- Usage progress bars ---- */
QProgressBar {
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    background: rgba(11, 18, 32, 0.65);
    text-align: center;
    padding: 2px;
    min-width: 120px;
    color: rgba(255,255,255,0.90);
}
QProgressBar#usagePctGreen::chunk   { background: #22c55e; border-radius: 8px; }
QProgressBar#usagePctYellow::chunk  { background: #facc15; border-radius: 8px; }
QProgressBar#usagePctOrange::chunk  { background: #f59e0b; border-radius: 8px; }
QProgressBar#usagePctRed::chunk     { background: #ef4444; border-radius: 8px; }
QProgressBar#usagePctNeutral::chunk { background: rgba(255,255,255,0.18); border-radius: 8px; }

/* --- TenantRuleDialog zone tiles (QToolButton) --- */
QToolButton#zoneTile {
    border: 2px solid rgba(255,255,255,0.14);
    border-radius: 10px;
    padding: 8px 10px;
    background: rgba(11, 18, 32, 0.65);
    color: rgba(255,255,255,0.92);
    font-weight: 600;
    min-height: 44px;
}
QToolButton#zoneTile:hover {
    border: 2px solid rgba(255,255,255,0.28);
    background: rgba(255,255,255,0.06);
}
/* conflicts property: -1 unknown, 0 ok, >0 bad */
QToolButton#zoneTile[conflicts="-1"] { border-color: rgba(255,255,255,0.18); background: rgba(255,255,255,0.03); }
QToolButton#zoneTile[conflicts="0"]  { border-color: rgba(34,197,94,0.85);  background: rgba(34,197,94,0.10); }
/* QSS не умеет [conflicts>0], поэтому conflicts_bad */
QToolButton#zoneTile[conflicts_bad="1"] { border-color: rgba(239,68,68,0.90); background: rgba(239,68,68,0.10); }
/* selected flag */
QToolButton#zoneTile[selected="true"] { background: rgba(96,165,250,0.16); border-color: rgba(96,165,250,0.95); }
/* selected + ok/bad overrides */
QToolButton#zoneTile[selected="true"][conflicts="0"] { background: rgba(34,197,94,0.18); border-color: rgba(34,197,94,0.90); }
QToolButton#zoneTile[selected="true"][conflicts_bad="1"] { background: rgba(239,68,68,0.18); border-color: rgba(239,68,68,0.95); }
"""
