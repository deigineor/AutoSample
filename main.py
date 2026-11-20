"""AutoSample — автоматичне семплування хардварних синтезаторів."""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from autosample.ui import style
from autosample.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AutoSample")
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(style.BG))
    pal.setColor(QPalette.Base, QColor(style.PANEL2))
    pal.setColor(QPalette.Text, QColor(style.TEXT))
    pal.setColor(QPalette.WindowText, QColor(style.TEXT))
    pal.setColor(QPalette.Button, QColor(style.PANEL2))
    pal.setColor(QPalette.ButtonText, QColor(style.TEXT))
    pal.setColor(QPalette.Highlight, QColor(style.ACCENT_DIM))
    app.setPalette(pal)
    app.setStyleSheet(style.QSS)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
