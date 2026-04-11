"""Background worker for desktop GUI analysis execution."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from PySide6.QtCore import QObject, Signal, Slot

from chart_view import save_combined_chart, save_env_mask_v4_report
from config import Settings, validate_data_mode, validate_logic_type
from data_source import (
    fetch_alpha_vantage_ohlc,
    load_csv_fallback,
    load_local_symbol_timeframe_csv,
    save_ohlc_to_local_csv,
)
from pattern_finder import add_features, find_similar_patterns


class AnalysisWorker(QObject):
    """Run analysis in background thread and emit progress/result signals."""

    progress = Signal(str, int)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    @Slot()
    def run(self) -> None:
        try:
            validate_logic_type(self.settings.logic_type)
            validate_data_mode(self.settings.data_mode)

            self.progress.emit("データ取得中...", 15)
            df, source_label, fetched_at = self._load_data_by_mode(self.settings)

            self.progress.emit("特徴量計算中...", 40)
            df = add_features(df, self.settings.ma_window)
            df = df.dropna(subset=["ma", "gap"]).reset_index(drop=True)
            if df.empty:
                raise ValueError("特徴量計算後に有効データがありません。")

            self.progress.emit("類似パターン探索中...", 65)
            matches = find_similar_patterns(df, self.settings)

            self.progress.emit("チャート生成中...", 85)
            if self.settings.logic_type == "env_mask_zscore_v4":
                report_path = save_env_mask_v4_report(
                    df,
                    self.settings,
                    matches,
                    output_dir=self.settings.charts_dir,
                )
            else:
                report_path = save_combined_chart(
                    df,
                    self.settings,
                    matches,
                    output_dir=self.settings.charts_dir,
                )

            self.progress.emit("完了", 100)
            self.finished.emit(
                {
                    "settings": asdict(self.settings),
                    "source_label": source_label,
                    "fetched_at": fetched_at,
                    "report_path": str(report_path),
                    "candidates": [self._candidate_to_dict(c) for c in matches],
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))

    def _load_data_by_mode(self, settings: Settings) -> tuple[pd.DataFrame, str, str]:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if settings.data_mode == "local":
            try:
                df = load_local_symbol_timeframe_csv(settings)
                return df, "local CSV", "N/A"
            except Exception:
                # local指定時も最低限サンプルにフォールバック
                df = load_csv_fallback(settings)
                return df, "local fallback(sample)", "N/A"

        # latest mode
        try:
            df = fetch_alpha_vantage_ohlc(settings)
            save_ohlc_to_local_csv(df, settings)
            return df, "latest API", now_str
        except Exception as api_exc:
            if settings.fallback_to_local:
                try:
                    df = load_local_symbol_timeframe_csv(settings)
                    return df, f"latest失敗→local使用 ({api_exc})", "N/A"
                except Exception:
                    df = load_csv_fallback(settings)
                    return df, f"latest失敗→sample使用 ({api_exc})", "N/A"
            raise RuntimeError(f"API取得失敗: {api_exc}")

    @staticmethod
    def _candidate_to_dict(candidate: Any) -> Dict[str, Any]:
        return {
            "rank": candidate.rank,
            "candidate_start_datetime": str(candidate.candidate_start_datetime),
            "score": candidate.score,
            "future_return": candidate.future_return,
            "candidate_gap": candidate.candidate_gap,
            "logic_type": candidate.logic_type,
            "score_breakdown": candidate.score_breakdown,
            "summary_stats": candidate.summary_stats,
        }
