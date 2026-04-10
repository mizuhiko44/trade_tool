"""
FX Pattern Tool (CLI)
====================

セットアップ方法:
1. Python 3.10+ を用意
2. 仮想環境を作成して有効化
   - python -m venv .venv
   - source .venv/bin/activate  (Windows: .venv\\Scripts\\activate)
3. 依存関係をインストール
   - pip install -r requirements.txt

.env の作り方:
1. .env.example をコピー
   - cp .env.example .env
2. .env の ALPHAVANTAGE_API_KEY に自分のキーを設定

実行方法:
- python app.py

設定変更方法:
- config.py の Settings 値を変更
  (symbol, timeframe, pattern_length, future_length, top_k, ma_window など)

注意事項:
- API制限やキー未設定時は sample_data のCSVへ自動フォールバック
- 日足/時間足どちらでも ma_window は「200本平均」として共通処理
- 本ツールは類似パターン可視化用で、売買シグナルは生成しない
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from chart_view import save_combined_chart
from config import get_settings
from data_source import load_ohlc_data
from pattern_finder import add_features, find_similar_patterns
from utils import ensure_dir, log_info


def validate_minimum_data(df: pd.DataFrame) -> None:
    """Guard against empty/too-short datasets."""

    if df is None or df.empty:
        raise ValueError("Loaded OHLC data is empty.")


def print_summary(df: pd.DataFrame, symbol: str, timeframe: str, pattern_length: int) -> None:
    """Print main summary block required by specification."""

    current_close = float(df["close"].iloc[-1])
    current_ma = float(df["ma"].iloc[-1])
    current_gap = float(df["gap"].iloc[-1])

    print("\n=== Current Status ===")
    print(f"symbol: {symbol}")
    print(f"timeframe: {timeframe}")
    print(f"data_count: {len(df)}")
    print(f"current_close: {current_close:.6f}")
    print(f"current_ma: {current_ma:.6f}")
    print(f"current_gap: {current_gap:.6f}")
    print(f"target_start_datetime: {df['datetime'].iloc[-pattern_length]}")


def main() -> int:
    """Main orchestration for loading, analysis, and chart output."""

    settings = get_settings()

    # Ensure charts directory exists.
    ensure_dir("charts")

    try:
        log_info("Loading OHLC data...")
        df = load_ohlc_data(settings)
        validate_minimum_data(df)

        log_info("Calculating features (ma, gap)...")
        df = add_features(df, settings.ma_window)
        df = df.dropna(subset=["ma", "gap"]).reset_index(drop=True)

        if df.empty:
            raise ValueError("No rows left after ma/gap calculation. Increase dataset length.")

        print_summary(df, settings.symbol, settings.timeframe, settings.pattern_length)

        log_info("Searching similar historical patterns...")
        matches = find_similar_patterns(df, settings)

        print("\n=== Similar Candidates ===")
        for m in matches:
            print(
                f"{m.rank} | {m.candidate_start_datetime} "
                f"| score={m.score:.4f} "
                f"| gap={m.candidate_gap:.4f} "
                f"| future_return={m.future_return:.4f}"
            )

        report_path = save_combined_chart(df, settings, matches, output_dir="charts")
        print(f"\nChart saved: {report_path}")

        # 改善案（将来拡張のためのメモ）:
        # 1) 類似度にボラティリティや出来高（利用可能時）を追加して多面的評価にする。
        # 2) 設定をJSON/CLI引数化し、複数シンボル一括バッチ実行に対応する。
        # 3) 候補区間の重複抑制（NMS的なロジック）を導入し、候補の多様性を高める。

        return 0
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
