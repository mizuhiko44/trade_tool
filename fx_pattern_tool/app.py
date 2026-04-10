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
  (logic_type, symbol, timeframe, pattern_length, candle_pattern_length など)
"""

from __future__ import annotations

import sys

import pandas as pd

from chart_view import save_combined_chart
from config import get_settings, validate_logic_type
from data_source import load_ohlc_data
from pattern_finder import add_features, find_similar_patterns
from utils import ensure_dir, log_info


def validate_minimum_data(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        raise ValueError("Loaded OHLC data is empty.")


def print_summary(df: pd.DataFrame, symbol: str, timeframe: str, logic_type: str, pattern_length: int) -> None:
    current_close = float(df["close"].iloc[-1])
    current_ma = float(df["ma"].iloc[-1])
    current_gap = float(df["gap"].iloc[-1])

    print("\n=== Current Status ===")
    print(f"symbol: {symbol}")
    print(f"timeframe: {timeframe}")
    print(f"logic_type: {logic_type}")
    print(f"data_count: {len(df)}")
    print(f"current_close: {current_close:.6f}")
    print(f"current_ma: {current_ma:.6f}")
    print(f"current_gap: {current_gap:.6f}")
    print(f"target_start_datetime: {df['datetime'].iloc[-pattern_length]}")


def main() -> int:
    settings = get_settings()
    validate_logic_type(settings.logic_type)
    ensure_dir("charts")

    try:
        log_info("Loading OHLC data...")
        df = load_ohlc_data(settings)
        validate_minimum_data(df)

        log_info("Calculating features (ma, gap)...")
        df = add_features(df, settings.ma_window)
        df = df.dropna(subset=["ma", "gap"]).reset_index(drop=True)

        active_pattern_length = (
            settings.candle_pattern_length if settings.logic_type == "candle_shape_v2" else settings.pattern_length
        )
        print_summary(df, settings.symbol, settings.timeframe, settings.logic_type, active_pattern_length)

        log_info("Searching similar historical patterns...")
        matches = find_similar_patterns(df, settings)

        print("\n=== Similar Candidates ===")
        for m in matches:
            base = (
                f"{m.rank} | {m.candidate_start_datetime} "
                f"| final_score={m.score:.4f} "
                f"| gap={m.candidate_gap:.4f} "
                f"| future_return={m.future_return:.4f}"
            )
            if m.logic_type == "candle_shape_v2":
                s = m.summary_stats
                base += (
                    f" | avg_body={s.get('average_body_ratio', 0):.4f}"
                    f" | avg_upper={s.get('average_upper_wick_ratio', 0):.4f}"
                    f" | avg_lower={s.get('average_lower_wick_ratio', 0):.4f}"
                    f" | bull={int(s.get('bullish_count', 0))}"
                    f" | bear={int(s.get('bearish_count', 0))}"
                    f" | avg_ma_gap={s.get('average_ma_gap_ratio', 0):.4f}"
                    f" | dir_miss={int(s.get('direction_mismatch_count', 0))}"
                    f" | cat_miss={int(s.get('category_mismatch_count', 0))}"
                    f" | pair_miss={int(s.get('pair_mismatch_count', 0))}"
                )
            print(base)

        report_path = save_combined_chart(df, settings, matches, output_dir="charts")
        print(f"\nChart saved: {report_path}")
        return 0
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
