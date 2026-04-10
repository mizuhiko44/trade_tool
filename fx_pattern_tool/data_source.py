"""Data acquisition for FX OHLC from Alpha Vantage, with CSV fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

from config import Settings, get_local_csv_path
from utils import ensure_dir, log_warn, split_fx_symbol


REQUIRED_COLUMNS = ["datetime", "open", "high", "low", "close"]


def _normalize_ohlc_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "datetime" not in out.columns:
        out = out.reset_index().rename(columns={out.columns[0]: "datetime"})

    for col in ["open", "high", "low", "close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce", utc=False)
    out = out.dropna(subset=REQUIRED_COLUMNS).copy()
    out = out.sort_values("datetime").reset_index(drop=True)

    return out[REQUIRED_COLUMNS]


def _parse_alpha_vantage_response(payload: Dict[str, object], timeframe: str) -> pd.DataFrame:
    if timeframe == "daily":
        ts_key = "Time Series FX (Daily)"
    elif timeframe == "weekly":
        ts_key = "Time Series FX (Weekly)"
    else:
        ts_key = f"Time Series FX ({timeframe})"

    if ts_key not in payload:
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
    elif settings.timeframe == "weekly":
        params = {
            "function": "FX_WEEKLY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "apikey": api_key,
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


def load_csv_file(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {missing}")

    return _normalize_ohlc_df(df)


def load_csv_fallback(settings: Settings, csv_path: Optional[str] = None) -> pd.DataFrame:
    path = Path(csv_path or settings.fallback_csv_path)
    return load_csv_file(path)


def load_local_symbol_timeframe_csv(settings: Settings) -> pd.DataFrame:
    local_path = get_local_csv_path(settings)
    return load_csv_file(local_path)


def save_ohlc_to_local_csv(df: pd.DataFrame, settings: Settings) -> Path:
    ensure_dir(settings.data_dir)
    save_path = get_local_csv_path(settings)
    df.to_csv(save_path, index=False)
    return save_path


def load_ohlc_data(settings: Settings) -> pd.DataFrame:
    if settings.data_source != "alpha_vantage":
        log_warn(
            f"Unsupported data_source={settings.data_source}. Falling back to CSV immediately."
        )
        return load_csv_fallback(settings)

    try:
        return fetch_alpha_vantage_ohlc(settings)
    except Exception as exc:
        log_warn(f"API fetch failed ({exc}). Falling back to CSV: {settings.fallback_csv_path}")
        return load_csv_fallback(settings)
