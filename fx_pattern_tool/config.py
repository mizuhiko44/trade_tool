"""Configuration for FX pattern search tool."""

from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings for data fetch, analysis, and output."""

    # 共通設定
    symbol: str = "USDJPY"
    timeframe: str = "daily"  # e.g. daily, weekly, 60min, 15min
    data_source: str = "alpha_vantage"

    # logic_type:
    #   "close_pattern_v1"   : Close系列 + MA GAP
    #   "candle_shape_v2"    : ローソク足形状 + 並び順重視
    #   "ma_gap_structure_v1": 200EMA/200SMA/Close の位置関係重視
    logic_type: str = "close_pattern_v1"

    # 共通探索設定
    top_k: int = 3
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
    candidate_chart_future_bars: int = 5  # candidate chart horizon (bars)

    # Fallback CSV path
    fallback_csv_path: str = "sample_data/sample_usdjpy_daily.csv"

    # API settings
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    request_timeout_sec: int = 30


def get_available_logic_types() -> list[str]:
    """Return all supported logic names."""

    return [
        "close_pattern_v1",
        "candle_shape_v2",
        "ma_gap_structure_v1",
    ]


def validate_logic_type(logic_type: str) -> None:
    """Validate logic name and raise explicit error when unsupported."""

    if logic_type not in get_available_logic_types():
        raise ValueError(
            f"Unsupported logic_type: {logic_type}. "
            f"Available: {get_available_logic_types()}"
        )


def get_settings() -> Settings:
    """Return default settings with validated logic_type."""

    settings = Settings()
    validate_logic_type(settings.logic_type)
    return settings
