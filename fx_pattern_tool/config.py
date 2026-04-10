"""Configuration for FX pattern search tool."""

from dataclasses import dataclass


@dataclass
class Settings:
    """Runtime settings for data fetch, analysis, and output."""

    symbol: str = "USDJPY"
    timeframe: str = "daily"  # e.g. daily, 60min, 15min
    pattern_length: int = 30
    future_length: int = 10
    top_k: int = 3
    ma_window: int = 200
    exclude_recent_bars: int = 60
    gap_weight: float = 0.5
    data_source: str = "alpha_vantage"

    # Fallback CSV path (used when API key is missing or API call fails)
    fallback_csv_path: str = "sample_data/sample_usdjpy_daily.csv"

    # API settings
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    request_timeout_sec: int = 30


def get_settings() -> Settings:
    """Return default settings.

    This function exists to allow future extension (e.g. JSON loading,
    environment overrides, CLI flags) without changing app.py.
    """

    return Settings()
