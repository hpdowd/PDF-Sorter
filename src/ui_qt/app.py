"""Qt application entry point."""
import logging
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src import __version__, utils
from src.ui_qt import theme

logger = logging.getLogger("ocr_file_sorter.gui")


def main():
    utils.setup_logging()
    logger.info("OCR File Sorter v%s starting", __version__)
    utils.ensure_mappings_seeded()

    app = QApplication(sys.argv)
    app.setApplicationName("OCR File Sorter")
    app.setStyleSheet(theme.app_qss())
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "icons", "sorterIcon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Imported after the QApplication exists, matching Qt's expectations for
    # any widget-level module state.
    from src.ui_qt.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
