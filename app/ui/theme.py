# app/ui/theme.py

DARK_APP_QSS = """
/* ---- Base ---- */
QMainWindow, QWidget {
    background: #0b1220;
    color: rgba(255, 255, 255, 0.88);
    font-size: 13px;
}

QToolTip {
    background: rgba(2, 6, 23, 0.95);
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
    background: rgba(255, 255, 255, 0.04);
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
QTabBar::tab:hover {
    border-color: rgba(255, 255, 255, 0.22);
}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {
    background: rgba(2, 6, 23, 0.40);
    color: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
    padding: 8px 10px;
    selection-background-color: rgba(99, 102, 241, 0.55);
}
QLineEdit::placeholder { color: rgba(226, 232, 240, 0.45); }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid rgba(99, 102, 241, 0.95);
    background: rgba(2, 6, 23, 0.52);
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
QPushButton:pressed {
    background: rgba(255, 255, 255, 0.07);
}
QPushButton:disabled {
    color: rgba(226, 232, 240, 0.35);
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.08);
}

/* Optional: если хочешь “primary” как на логине */
QPushButton#primary {
    color: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(99, 102, 241, 0.75);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(99, 102, 241, 1.0),
        stop:1 rgba(34, 211, 238, 1.0)
    );
}
QPushButton#primary:hover {
    border-color: rgba(255, 255, 255, 0.22);
}

/* ---- Checkbox ---- */
QCheckBox { spacing: 8px; color: rgba(226, 232, 240, 0.82); }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border-radius: 6px;
    background: rgba(2, 6, 23, 0.40);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
QCheckBox::indicator:checked {
    background: rgba(99, 102, 241, 0.95);
    border-color: rgba(99, 102, 241, 0.95);
}

/* ---- Table ---- */
QTableWidget, QTableView {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 12px;
    gridline-color: transparent;
    alternate-background-color: rgba(255, 255, 255, 0.03);
    selection-background-color: rgba(99, 102, 241, 0.28);
    selection-color: rgba(255, 255, 255, 0.92);
}
QHeaderView::section {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(226, 232, 240, 0.82);
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.10);
    font-weight: 800;
}
QTableView::item {
    padding: 6px 10px;
    border: none;
}
QTableView::item:selected {
    background: rgba(99, 102, 241, 0.28);
}

/* ---- Scrollbar (чуть аккуратнее) ---- */
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
QDialog {
    background: #0b1220;
}
QMessageBox QLabel {
    color: rgba(255, 255, 255, 0.88);
}
"""
