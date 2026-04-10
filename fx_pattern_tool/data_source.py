"""Data acquisition for FX OHLC from Alpha Vantage, with CSV fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

from config import Settings
from utils import log_warn, split_fx_symbol


REQUIRED_COLUMNS = ["datetime", "open", "high", "low", "close"]


def _normalize_ohlc_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize DataFrame into required OHLC schema.

    Expected output columns: datetime, open, high, low, close
    """

    out = df.copy()

    if "datetime" not in out.columns:
        # API frame usually has timestamp in index
        out = out.reset_index().rename(columns={out.columns[0]: "datetime"})

    # Ensure columns exist and are numeric
    for col in ["open", "high", "low", "close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce", utc=False)
    out = out.dropna(subset=REQUIRED_COLUMNS).copy()
    out = out.sort_values("datetime").reset_index(drop=True)

    return out[REQUIRED_COLUMNS]


def _parse_alpha_vantage_response(payload: Dict[str, object], timeframe: str) -> pd.DataFrame:
    """Parse Alpha Vantage response payload to DataFrame."""

    if timeframe == "daily":
        ts_key = "Time Series FX (Daily)"
    else:
        ts_key = f"Time Series FX ({timeframe})"

    if ts_key not in payload:
        # API may return note or error message for limits/invalid params.
        raise ValueError(f"Alpha Vantage response missing '{ts_key}'. Keys: {list(payload.keys())}")

    raw_ts = payload[ts_key]
    rows = []
    for dt_str, values in raw_ts.items():
        rows.append(
            {
                "datetime": dt_str,
                "open": values.get("1. open"),
                "high": values.get("2. high"),
                "low": values.get("3. low"),
                "close": values.get("4. close"),
            }
        )

    if not rows:
        raise ValueError("Alpha Vantage returned empty time series.")

    return _normalize_ohlc_df(pd.DataFrame(rows))


def fetch_alpha_vantage_ohlc(settings: Settings) -> pd.DataFrame:
    """Fetch OHLC from Alpha Vantage for configured symbol/timeframe."""

    load_dotenv()
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ALPHAVANTAGE_API_KEY is not set in .env.")

    from_symbol, to_symbol = split_fx_symbol(settings.symbol)

    if settings.timeframe == "daily":
        params = {
            "function": "FX_DAILY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "apikey": api_key,
            "outputsize": "full",
        }
    else:
        params = {
            "function": "FX_INTRADAY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "interval": settings.timeframe,
            "apikey": api_key,
            "outputsize": "full",
        }

    response = requests.get(
        settings.alpha_vantage_base_url, params=params, timeout=settings.request_timeout_sec
    )
    response.raise_for_status()
    payload = response.json()

    return _parse_alpha_vantage_response(payload, settings.timeframe)


def load_csv_fallback(settings: Settings, csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load OHLC from local CSV fallback."""

    path = Path(csv_path or settings.fallback_csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Fallback CSV not found: {path}")

    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Fallback CSV is missing columns: {missing}")

    return _normalize_ohlc_df(df)


def load_ohlc_data(settings: Settings) -> pd.DataFrame:
    """Try API first, then fallback to local CSV with warning logs."""

    if settings.data_source != "alpha_vantage":
        log_warn(
            f"Unsupported data_source={settings.data_source}. Falling back to CSV immediately."
        )
        return load_csv_fallback(settings)

    try:
        return fetch_alpha_vantage_ohlc(settings)
    except Exception as exc:  # broad by design for robust fallback
        log_warn(f"API fetch failed ({exc}). Falling back to CSV: {settings.fallback_csv_path}")
        return load_csv_fallback(settings)
