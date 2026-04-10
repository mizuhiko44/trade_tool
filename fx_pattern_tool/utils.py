"""Utility helpers for logging, filesystem operations, and symbol parsing."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Tuple


def log_info(message: str) -> None:
    """Print an info-level log message with timestamp."""

    print(f"[INFO {datetime.utcnow().isoformat(timespec='seconds')}Z] {message}")


def log_warn(message: str) -> None:
    """Print a warning-level log message with timestamp."""

    print(f"[WARN {datetime.utcnow().isoformat(timespec='seconds')}Z] {message}")


def ensure_dir(path: str | Path) -> Path:
    """Create directory if it does not exist and return Path object."""

    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def split_fx_symbol(symbol: str) -> Tuple[str, str]:
    """Split pair like USDJPY into (USD, JPY).

    Raises:
        ValueError: if symbol is not 6 alphabetic characters.
    """

    normalized = symbol.strip().upper()
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError(
            f"Invalid symbol '{symbol}'. Expected 6 letters like USDJPY or EURUSD."
        )
    return normalized[:3], normalized[3:]
