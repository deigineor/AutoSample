"""Темна тема."""
from pathlib import Path

ICONS = (Path(__file__).parent / "icons").as_posix()

BG = "#121418"
PANEL = "#1a1d23"
PANEL2 = "#22262e"
BORDER = "#2c313b"
TEXT = "#d9dde5"
MUTED = "#8a92a3"
ACCENT = "#4fd1c5"
ACCENT_DIM = "#2a6f69"
REC = "#ff5c5c"
WARN = "#ffb347"
ACTIVE = "#ff9f43"

QSS = f"""
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QWidget#Root {{ background: {BG}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}

QFrame#Header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel#Logo {{ font-size: 15pt; font-weight: 700; letter-spacing: 2px; color: {ACCENT}; }}
QLabel#LogoSub {{ color: {MUTED}; font-size: 9pt; }}
QLabel#Summary {{ color: {MUTED}; }}
QLabel#Muted {{ color: {MUTED}; font-size: 9pt; }}
QLabel#Status {{ color: {MUTED}; }}

QFrame#Card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {PANEL}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a414d; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QGroupBox {{
    border: none; margin-top: 18px; padding-top: 6px; font-weight: 700; color: {MUTED};
    font-size: 8.5pt; text-transform: uppercase;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 2px; padding: 0; color: {MUTED}; letter-spacing: 1px; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 5px; padding: 4px 6px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: #5b6270; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 14px; border: none; background: transparent;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({ICONS}/up.svg); width: 9px; height: 6px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({ICONS}/down.svg); width: 9px; height: 6px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({ICONS}/down.svg); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{
    background: {PANEL2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DIM}; outline: 0;
}}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER}; background: {PANEL2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QCheckBox::indicator:hover {{ border: 1px solid {ACCENT}; }}

QPushButton {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; font-weight: 600;
}}
QPushButton:hover {{ border: 1px solid {ACCENT}; color: #ffffff; }}
QPushButton:pressed {{ background: {ACCENT_DIM}; }}
QPushButton:disabled {{ color: #5b6270; border-color: {BORDER}; }}
QPushButton#Primary {{
    background: {ACCENT}; color: #0d1214; border: none; padding: 9px 22px; font-size: 11pt;
}}
QPushButton#Primary:hover {{ background: #6fe3d8; }}
QPushButton#Primary:disabled {{ background: {ACCENT_DIM}; color: #0d1214; }}
QPushButton#Danger {{ background: {REC}; color: #1a0d0d; border: none; padding: 9px 22px; font-size: 11pt; }}
QPushButton#Danger:hover {{ background: #ff7b7b; }}
QPushButton#Danger:disabled {{ background: #5a2c2c; color: #1a0d0d; }}
QPushButton#Flat {{ background: transparent; border: 1px solid transparent; color: {MUTED}; padding: 5px 9px; }}
QPushButton#Flat:hover {{ border: 1px solid {BORDER}; color: {TEXT}; }}

QProgressBar {{
    background: {PANEL2}; border: none; border-radius: 3px; height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QTableWidget {{
    background: {PANEL}; alternate-background-color: #1d2128; border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: transparent; selection-background-color: {ACCENT_DIM}; selection-color: #ffffff;
}}
QTableWidget::item {{ padding: 2px 6px; border: none; }}
QHeaderView::section {{
    background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px; font-weight: 600; font-size: 9pt;
}}
QTableCornerButton::section {{ background: {PANEL}; border: none; }}

QPlainTextEdit#Log {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {PANEL2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMessageBox {{ background: {PANEL}; }}
"""
