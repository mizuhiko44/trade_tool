"""Configuration for FX Pattern Analyzer Desktop."""

from dataclasses import dataclass
from pathlib import Path

# UI choices
AVAILABLE_SYMBOLS = ["USDJPY", "EURUSD", "GBPJPY", "EURJPY"]
AVAILABLE_TIMEFRAMES = ["daily", "60min", "15min", "weekly"]
AVAILABLE_LOGIC_TYPES = [
    "close_pattern_v1",
    "candle_shape_v2",
    "ma_gap_structure_v1",
]
AVAILABLE_DATA_MODES = ["local", "latest"]

LOGIC_LABELS = {
    "close_pattern_v1": "Closeパターン + GAP",
    "candle_shape_v2": "ローソク足形状 + 並び順",
    "ma_gap_structure_v1": "200EMA/200SMA ギャップ構造",
}

DEFAULT_SYMBOL = "USDJPY"
DEFAULT_TIMEFRAME = "daily"
DEFAULT_LOGIC_TYPE = "close_pattern_v1"
DEFAULT_DATA_MODE = "local"
DEFAULT_TOP_K = 3
DEFAULT_FALLBACK_TO_LOCAL = True


@dataclass
class Settings:
    """Runtime settings for data fetch, analysis, and output."""

    # 共通設定
    symbol: str = DEFAULT_SYMBOL
    timeframe: str = DEFAULT_TIMEFRAME
    data_source: str = "alpha_vantage"

    # logic_type:
    #   "close_pattern_v1"   : Close系列 + MA GAP
    #   "candle_shape_v2"    : ローソク足形状 + 並び順重視
    #   "ma_gap_structure_v1": 200EMA/200SMA/Close の位置関係重視
    logic_type: str = DEFAULT_LOGIC_TYPE

    # GUI data mode
    data_mode: str = DEFAULT_DATA_MODE  # local | latest
    fallback_to_local: bool = DEFAULT_FALLBACK_TO_LOCAL

    # 共通探索設定
    top_k: int = DEFAULT_TOP_K
    exclude_recent_bars: int = 60
    future_length: int = 10
    ma_window: int = 200

    # close_pattern_v1 settings
    pattern_length: int = 30
    gap_weight: float = 0.5

    # candle_shape_v2 settings
    candle_pattern_length: int = 10
    candle_weight_ma_gap: float = 2.0
    candle_weight_upper_wick: float = 1.5
    candle_weight_lower_wick: float = 1.5
    candle_weight_body: float = 2.0
    candle_weight_direction: float = 1.0

    sequence_weight_direction: float = 2.0
    sequence_weight_category: float = 2.0
    sequence_weight_pair: float = 2.5

    aggregate_weight_body: float = 1.5
    aggregate_weight_upper: float = 1.2
    aggregate_weight_lower: float = 1.2
    aggregate_weight_bullish: float = 1.0
    aggregate_weight_bearish: float = 1.0
    aggregate_weight_ma_gap: float = 1.5

    threshold_body_large: float = 0.6
    threshold_body_small: float = 0.2
    threshold_upper_wick_long: float = 0.4
    threshold_lower_wick_long: float = 0.4

    # ma_gap_structure_v1 settings
    ma_gap_pattern_length: int = 10
    ma_gap_weight_ema_sma: float = 1.5
    ma_gap_weight_close_ema: float = 2.0
    ma_gap_sign_penalty_ema_sma: float = 1.2
    ma_gap_sign_penalty_close_ema: float = 1.5
    ma_gap_aggregate_weight_ema_sma: float = 0.8
    ma_gap_aggregate_weight_close_ema: float = 1.0

    # chart
    candidate_chart_future_bars: int = 5

    # data path
    data_dir: str = "data"
    charts_dir: str = "charts"
    fallback_csv_path: str = "sample_data/sample_usdjpy_daily.csv"

    # API settings
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    request_timeout_sec: int = 30


def get_available_logic_types() -> list[str]:
    return AVAILABLE_LOGIC_TYPES.copy()


def validate_logic_type(logic_type: str) -> None:
    if logic_type not in get_available_logic_types():
        raise ValueError(
            f"Unsupported logic_type: {logic_type}. "
            f"Available: {get_available_logic_types()}"
        )


def validate_data_mode(data_mode: str) -> None:
    if data_mode not in AVAILABLE_DATA_MODES:
        raise ValueError(
            f"Unsupported data_mode: {data_mode}. "
            f"Available: {AVAILABLE_DATA_MODES}"
        )


def get_local_csv_path(settings: Settings) -> Path:
    return Path(settings.data_dir) / f"{settings.symbol}_{settings.timeframe}.csv"


def get_settings() -> Settings:
    settings = Settings()
    validate_logic_type(settings.logic_type)
    validate_data_mode(settings.data_mode)
    return settings
