"""Configuration for FX pattern search tool."""

from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings for data fetch, analysis, and output."""

    symbol: str = "USDJPY"
    timeframe: str = "daily"  # e.g. daily, weekly, 60min, 15min

    # Logic switch
    logic_type: str = "candle_shape_v2"  # close_pattern_v1 | candle_shape_v2

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

    # shared settings
    future_length: int = 10
    top_k: int = 3
    ma_window: int = 200
    exclude_recent_bars: int = 60
    data_source: str = "alpha_vantage"
    candidate_chart_future_bars: int = 5  # candidate chart horizon (bars)

    # Fallback CSV path (used when API key is missing or API call fails)
    fallback_csv_path: str = "sample_data/sample_usdjpy_daily.csv"

    # API settings
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    request_timeout_sec: int = 30


def get_settings() -> Settings:
    """Return default settings."""

    return Settings()
