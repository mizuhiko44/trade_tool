"""FX Pattern Analyzer Desktop entrypoint.

PySide6 が無い環境では Tkinter フォールバックGUIを起動する。
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from gui_main import FXPatternAnalyzerWindow

        app = QApplication(sys.argv)
        window = FXPatternAnalyzerWindow()
        window.show()
        return app.exec()
    except ModuleNotFoundError as exc:
        # Fallback path for environments without PySide6
        if "PySide6" not in str(exc):
            raise

        print("[WARN] PySide6 が見つかりません。Tkinter フォールバックGUIで起動します。")
        print("       PySide6版を使う場合: pip install PySide6 PySide6-WebEngine")
        from gui_main_tk import run_tk_app

        run_tk_app()
        return 0


if __name__ == "__main__":
    sys.exit(main())
