"""Pattern feature engineering and similarity search logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from config import Settings


@dataclass
class CandidateMatch:
    """A single similar historical pattern candidate."""

    rank: int
    start_idx: int
    end_idx: int
    candidate_start_datetime: pd.Timestamp
    score: float
    candidate_gap: float
    future_return: float


def normalize_series(series: pd.Series) -> np.ndarray:
    """Normalize series by start-point ratio: (x / x0) - 1."""

    arr = series.astype(float).to_numpy()
    if len(arr) == 0:
        return arr
    base = arr[0]
    if np.isclose(base, 0.0):
        # fallback to difference-based normalization if base is near zero
        return arr - base
    return (arr / base) - 1.0


def add_features(df: pd.DataFrame, ma_window: int) -> pd.DataFrame:
    """Add moving average and gap columns.

    gap = (close - ma) / ma
    """

    out = df.copy()
    out["ma"] = out["close"].rolling(ma_window).mean()
    out["gap"] = (out["close"] - out["ma"]) / out["ma"]
    return out


def find_similar_patterns(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    """Find top-k similar historical close patterns with gap-aware scoring."""

    required_cols = {"datetime", "close", "gap"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Input DataFrame missing columns: {missing}")

    pattern_length = settings.pattern_length
    future_length = settings.future_length
    top_k = settings.top_k

    if len(df) < settings.ma_window + pattern_length + future_length + settings.exclude_recent_bars:
        raise ValueError(
            "Not enough rows for analysis. Increase data amount or reduce pattern parameters."
        )

    target_start = len(df) - pattern_length
    target_end = len(df) - 1

    target_close = df["close"].iloc[target_start : target_end + 1]
    target_norm = normalize_series(target_close)

    target_gap = float(df["gap"].iloc[target_start])
    if np.isnan(target_gap):
        raise ValueError("Target gap is NaN. Ensure enough bars exist for moving average window.")

    max_candidate_start = len(df) - settings.exclude_recent_bars - pattern_length - future_length
    if max_candidate_start <= 0:
        raise ValueError("No candidate window left after exclude_recent_bars constraint.")

    candidates: List[CandidateMatch] = []
    for start_idx in range(0, max_candidate_start + 1):
        end_idx = start_idx + pattern_length - 1
        future_idx = end_idx + future_length

        candidate_close = df["close"].iloc[start_idx : end_idx + 1]
        candidate_norm = normalize_series(candidate_close)

        shape_distance = float(np.sum((target_norm - candidate_norm) ** 2))

        candidate_gap = float(df["gap"].iloc[start_idx])
        if np.isnan(candidate_gap):
            continue

        gap_distance = abs(target_gap - candidate_gap)
        score = shape_distance + settings.gap_weight * gap_distance

        end_close = float(df["close"].iloc[end_idx])
        future_close = float(df["close"].iloc[future_idx])
        if np.isclose(end_close, 0.0):
            continue
        future_return = (future_close / end_close) - 1.0

        candidates.append(
            CandidateMatch(
                rank=0,
                start_idx=start_idx,
                end_idx=end_idx,
                candidate_start_datetime=df["datetime"].iloc[start_idx],
                score=score,
                candidate_gap=candidate_gap,
                future_return=float(future_return),
            )
        )

    if not candidates:
        raise ValueError("No valid candidates were found.")

    candidates_sorted = sorted(candidates, key=lambda x: x.score)[:top_k]
    for i, c in enumerate(candidates_sorted, start=1):
        c.rank = i

    return candidates_sorted
