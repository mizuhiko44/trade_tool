"""Main GUI window for FX Pattern Analyzer Desktop."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import (
    AVAILABLE_DATA_MODES,
    AVAILABLE_LOGIC_TYPES,
    AVAILABLE_SYMBOLS,
    AVAILABLE_TIMEFRAMES,
    LOGIC_LABELS,
    Settings,
)
from gui_worker import AnalysisWorker

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:  # fallback when webengine is unavailable
    QWebEngineView = None


class FXPatternAnalyzerWindow(QMainWindow):
    """Single-window desktop UI."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FX Pattern Analyzer Desktop")
        self.resize(1300, 900)

        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None

        self._build_ui()
        self._set_idle_status()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(self._build_setting_group())
        root.addWidget(self._build_status_group())
        root.addWidget(self._build_summary_group())
        root.addWidget(self._build_table_group())
        root.addWidget(self._build_chart_group())

    def _build_setting_group(self) -> QGroupBox:
        g = QGroupBox("設定")
        lay = QFormLayout(g)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(AVAILABLE_SYMBOLS)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(AVAILABLE_TIMEFRAMES)

        self.logic_combo = QComboBox()
        for logic in AVAILABLE_LOGIC_TYPES:
            self.logic_combo.addItem(f"{LOGIC_LABELS.get(logic, logic)} ({logic})", userData=logic)
        self.logic_combo.currentIndexChanged.connect(self._on_logic_changed)

        self.data_mode_combo = QComboBox()
        self.data_mode_combo.addItems(AVAILABLE_DATA_MODES)

        self.topk_spin = QSpinBox()
        self.topk_spin.setRange(1, 10)
        self.topk_spin.setValue(3)

        self.pattern_len_spin = QSpinBox()
        self.pattern_len_spin.setRange(5, 200)
        self.pattern_len_spin.setValue(30)

        self.fallback_check = QCheckBox("latest失敗時にlocalへフォールバック")
        self.fallback_check.setChecked(True)

        self.run_button = QPushButton("分析実行")
        self.run_button.clicked.connect(self._run_analysis)

        lay.addRow("通貨ペア", self.symbol_combo)
        lay.addRow("時間足", self.timeframe_combo)
        lay.addRow("分析ロジック", self.logic_combo)
        lay.addRow("データ取得方法", self.data_mode_combo)
        lay.addRow("候補件数(top_k)", self.topk_spin)
        lay.addRow("パターン比較本数", self.pattern_len_spin)
        lay.addRow("", self.fallback_check)
        lay.addRow("", self.run_button)

        return g

    def _build_status_group(self) -> QGroupBox:
        g = QGroupBox("ステータス")
        lay = QVBoxLayout(g)

        self.status_label = QLabel("待機中")
        self.api_time_label = QLabel("データ取得日時: -")
        self.source_label = QLabel("実際の使用データ: -")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        lay.addWidget(self.status_label)
        lay.addWidget(self.api_time_label)
        lay.addWidget(self.source_label)
        lay.addWidget(self.progress_bar)
        return g

    def _build_summary_group(self) -> QGroupBox:
        g = QGroupBox("条件サマリー")
        lay = QVBoxLayout(g)
        self.summary_label = QLabel("未実行")
        self.summary_label.setWordWrap(True)
        lay.addWidget(self.summary_label)
        return g

    def _build_table_group(self) -> QGroupBox:
        g = QGroupBox("候補一覧")
        lay = QVBoxLayout(g)

        self.result_table = QTableWidget(0, 4)
        self.result_table.setHorizontalHeaderLabels(["rank", "candidate_start_datetime", "score", "future_return"])
        lay.addWidget(self.result_table)
        return g

    def _build_chart_group(self) -> QGroupBox:
        g = QGroupBox("チャート")
        lay = QVBoxLayout(g)

        if QWebEngineView is not None:
            self.chart_view = QWebEngineView()
        else:
            from PySide6.QtWidgets import QTextBrowser

            self.chart_view = QTextBrowser()
            self.chart_view.setPlainText("QWebEngineView未導入。charts/pattern_report.html を外部ブラウザで開いてください。")

        lay.addWidget(self.chart_view)
        return g

    def _on_logic_changed(self) -> None:
        logic = self.logic_combo.currentData()
        if logic == "close_pattern_v1":
            self.pattern_len_spin.setValue(30)
        else:
            self.pattern_len_spin.setValue(10)

    def _build_settings_from_ui(self) -> Settings:
        settings = Settings()
        settings.symbol = self.symbol_combo.currentText()
        settings.timeframe = self.timeframe_combo.currentText()
        settings.logic_type = self.logic_combo.currentData()
        settings.data_mode = self.data_mode_combo.currentText()
        settings.top_k = int(self.topk_spin.value())
        settings.fallback_to_local = self.fallback_check.isChecked()

        pattern_len = int(self.pattern_len_spin.value())
        if settings.logic_type == "close_pattern_v1":
            settings.pattern_length = pattern_len
        elif settings.logic_type == "candle_shape_v2":
            settings.candle_pattern_length = pattern_len
        elif settings.logic_type == "ma_gap_structure_v1":
            settings.ma_gap_pattern_length = pattern_len

        return settings

    def _run_analysis(self) -> None:
        settings = self._build_settings_from_ui()
        self.run_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("分析中...")

        self.worker_thread = QThread(self)
        self.worker = AnalysisWorker(settings)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)

        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_thread)

        self.worker_thread.start()

    def _on_progress(self, message: str, progress: int) -> None:
        self.status_label.setText(message)
        self.progress_bar.setValue(progress)

    def _on_finished(self, payload: Dict[str, Any]) -> None:
        self.status_label.setText("完了")
        self.progress_bar.setValue(100)
        self.run_button.setEnabled(True)

        settings = payload["settings"]
        self.api_time_label.setText(f"データ取得日時: {payload['fetched_at']}")
        self.source_label.setText(f"実際の使用データ: {payload['source_label']}")

        self.summary_label.setText(
            f"symbol={settings['symbol']} / timeframe={settings['timeframe']} / "
            f"logic={settings['logic_type']} / data_mode={settings['data_mode']} / "
            f"top_k={settings['top_k']} / fallback={settings['fallback_to_local']}"
        )

        self._fill_candidate_table(payload["candidates"], settings["logic_type"])
        self._show_chart(payload["report_path"])

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(f"エラー: {message}")
        self.progress_bar.setValue(0)
        self.run_button.setEnabled(True)
        QMessageBox.critical(self, "分析エラー", message)

    def _cleanup_thread(self) -> None:
        self.worker = None
        self.worker_thread = None

    def _fill_candidate_table(self, candidates: List[Dict[str, Any]], logic_type: str) -> None:
        common_cols = ["rank", "candidate_start_datetime", "score", "future_return"]
        if logic_type == "close_pattern_v1":
            extra_cols = ["candidate_gap", "shape_distance"]
        elif logic_type == "candle_shape_v2":
            extra_cols = [
                "average_body_ratio",
                "average_upper_wick_ratio",
                "average_lower_wick_ratio",
                "bullish_count",
                "bearish_count",
                "direction_mismatch_count",
                "category_mismatch_count",
                "pair_mismatch_count",
            ]
        else:
            extra_cols = [
                "average_ema_sma_gap_pct",
                "average_close_ema_gap_pct",
                "sign_match_ratio",
            ]

        headers = common_cols + extra_cols
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        self.result_table.setRowCount(len(candidates))

        for r, cand in enumerate(candidates):
            stats = cand.get("summary_stats", {})
            detail = cand.get("score_breakdown", {})
            values = {
                "rank": cand.get("rank"),
                "candidate_start_datetime": cand.get("candidate_start_datetime"),
                "score": f"{cand.get('score', 0):.6f}",
                "future_return": f"{cand.get('future_return', 0):.6f}",
                "candidate_gap": f"{cand.get('candidate_gap', 0):.6f}",
                "shape_distance": f"{detail.get('shape_distance', 0):.6f}",
                "average_body_ratio": f"{stats.get('average_body_ratio', 0):.6f}",
                "average_upper_wick_ratio": f"{stats.get('average_upper_wick_ratio', 0):.6f}",
                "average_lower_wick_ratio": f"{stats.get('average_lower_wick_ratio', 0):.6f}",
                "bullish_count": f"{stats.get('bullish_count', 0):.0f}",
                "bearish_count": f"{stats.get('bearish_count', 0):.0f}",
                "direction_mismatch_count": f"{stats.get('direction_mismatch_count', 0):.0f}",
                "category_mismatch_count": f"{stats.get('category_mismatch_count', 0):.0f}",
                "pair_mismatch_count": f"{stats.get('pair_mismatch_count', 0):.0f}",
                "average_ema_sma_gap_pct": f"{stats.get('average_ema_sma_gap_pct', 0):.6f}",
                "average_close_ema_gap_pct": f"{stats.get('average_close_ema_gap_pct', 0):.6f}",
                "sign_match_ratio": f"{stats.get('sign_match_ratio', 0):.6f}",
            }

            for c, h in enumerate(headers):
                self.result_table.setItem(r, c, QTableWidgetItem(str(values.get(h, ""))))

        self.result_table.resizeColumnsToContents()

    def _show_chart(self, report_path: str) -> None:
        p = Path(report_path).resolve()
        if QWebEngineView is not None and hasattr(self.chart_view, "setUrl"):
            from PySide6.QtCore import QUrl

            self.chart_view.setUrl(QUrl.fromLocalFile(str(p)))
        else:
            self.chart_view.setPlainText(f"チャート生成完了: {p}")

    def _set_idle_status(self) -> None:
        self.status_label.setText("待機中")
        self.progress_bar.setValue(0)
        self.api_time_label.setText("データ取得日時: -")
        self.source_label.setText("実際の使用データ: -")
