"""GUI bootstrap helper."""

from __future__ import annotations

import sys

from ..config import Config


def launch(config: Config | None = None) -> int:
    """Create the Qt application and show the main window.

    Imported lazily by the CLI so that non-GUI commands (like ``doctor``) don't
    require a display or the Qt runtime.
    """
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    return app.exec()
