"""Application entry: launch the PySide6 GUI."""

from __future__ import annotations

import os
import sys


def main() -> int:
    # High-DPI friendly before QApplication
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from batch_watermark import APP_DISPLAY_NAME
    from batch_watermark.gui.main_window import MainWindow

    # Qt6: PassThrough keeps native sharpness on Win laptop scaling
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setOrganizationName("ETBoos")
    app.setOrganizationDomain("github.com/ETBoos")
    # Compact global controls for small / scaled laptop screens
    app.setStyleSheet(
        """
        QPushButton {
            min-height: 22px;
            max-height: 28px;
            padding: 2px 10px;
            font-size: 12px;
        }
        QGroupBox {
            font-weight: 600;
            font-size: 12px;
            margin-top: 8px;
            padding-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }
        QLabel { font-size: 12px; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            min-height: 22px;
            max-height: 28px;
            font-size: 12px;
            padding: 1px 4px;
        }
        QListWidget { font-size: 12px; }
        """
    )

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
