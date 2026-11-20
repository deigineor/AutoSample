"""AutoSample — automatic sampling of hardware synthesizers."""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from autosample import i18n
from autosample.settings import Settings, config_dir
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
    try:
        i18n.set_language(Settings.load(config_dir() / "last_session.json").language)
    except Exception:
        pass  # no or unreadable config: stay in English
    show_window(app)
    sys.exit(app.exec())


def show_window(app, old=None):
    """Open a MainWindow; when the user switches language, close it (it saves its state) and open a fresh one."""
    if old is not None:
        app.setQuitOnLastWindowClosed(False)   # keep the event loop alive between the two windows
        old.close()
        old.deleteLater()
    w = MainWindow()
    w.languageChanged.connect(lambda: QTimer.singleShot(0, lambda: show_window(app, w)))
    w.show()
    app.setQuitOnLastWindowClosed(True)


if __name__ == "__main__":
    main()
