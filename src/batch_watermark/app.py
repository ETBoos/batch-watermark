"""Application entry: launch the PySide6 GUI."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from batch_watermark import APP_DISPLAY_NAME
    from batch_watermark.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setOrganizationName("ETBoos")
    app.setOrganizationDomain("github.com/ETBoos")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
