"""FX Pattern Analyzer Desktop entrypoint."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from gui_main import FXPatternAnalyzerWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = FXPatternAnalyzerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
