"""Pattern feature engineering and similarity search logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

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
    logic_type: str = "close_pattern_v1"
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    summary_stats: Dict[str, float] = field(default_factory=dict)


def normalize_series(series: pd.Series) -> np.ndarray:
    """Normalize series by start-point ratio: (x / x0) - 1."""

    arr = series.astype(float).to_numpy()
    if len(arr) == 0:
        return arr
    base = arr[0]
    if np.isclose(base, 0.0):
        return arr - base
    return (arr / base) - 1.0


def add_features(df: pd.DataFrame, ma_window: int) -> pd.DataFrame:
    """Add moving average and gap columns."""

    out = df.copy()
    out["ma"] = out["close"].rolling(ma_window).mean()
    out["gap"] = (out["close"] - out["ma"]) / out["ma"]
    return out


def build_candle_features(df: pd.DataFrame, ma_window: int) -> pd.DataFrame:
    """Build candle-shape feature set for candle_shape_v2."""

    out = add_features(df, ma_window)

    candle_range = out["high"] - out["low"]
    safe_range = candle_range.replace(0, np.nan)

    upper_wick = out["high"] - out[["open", "close"]].max(axis=1)
    lower_wick = out[["open", "close"]].min(axis=1) - out["low"]
    body = (out["close"] - out["open"]).abs()

    out["ma_gap_ratio"] = out["gap"]
    out["upper_wick_ratio"] = (upper_wick / safe_range).fillna(0.0)
    out["lower_wick_ratio"] = (lower_wick / safe_range).fillna(0.0)
    out["body_ratio"] = (body / safe_range).fillna(0.0)
    out["direction"] = np.where(out["close"] > out["open"], 1, np.where(out["close"] < out["open"], -1, 0))

    return out


def classify_candle_shape(row: pd.Series, settings: Settings) -> str:
    """Classify candle shape with deterministic priority."""

    if row["body_ratio"] >= settings.threshold_body_large:
        return "body_large"
    if row["body_ratio"] <= settings.threshold_body_small:
        return "body_small"
    if row["upper_wick_ratio"] >= settings.threshold_upper_wick_long:
        return "upper_wick_long"
    if row["lower_wick_ratio"] >= settings.threshold_lower_wick_long:
        return "lower_wick_long"
    return "balanced"


def calc_base_shape_score(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> float:
    """Score per-candle aligned feature distance."""

    direction_penalty = (target_block["direction"].to_numpy() != candidate_block["direction"].to_numpy()).astype(float)

    score = (
        settings.candle_weight_ma_gap
        * np.sum((target_block["ma_gap_ratio"].to_numpy() - candidate_block["ma_gap_ratio"].to_numpy()) ** 2)
        + settings.candle_weight_upper_wick
        * np.sum((target_block["upper_wick_ratio"].to_numpy() - candidate_block["upper_wick_ratio"].to_numpy()) ** 2)
        + settings.candle_weight_lower_wick
        * np.sum((target_block["lower_wick_ratio"].to_numpy() - candidate_block["lower_wick_ratio"].to_numpy()) ** 2)
        + settings.candle_weight_body
        * np.sum((target_block["body_ratio"].to_numpy() - candidate_block["body_ratio"].to_numpy()) ** 2)
        + settings.candle_weight_direction * np.sum(direction_penalty)
    )
    return float(score)


def calc_direction_sequence_penalty(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> tuple[float, int]:
    mismatch_count = int(np.sum(target_block["direction"].to_numpy() != candidate_block["direction"].to_numpy()))
    penalty = settings.sequence_weight_direction * (mismatch_count / len(target_block))
    return float(penalty), mismatch_count


def calc_category_sequence_penalty(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> tuple[float, int]:
    mismatch_count = int(np.sum(target_block["shape_category"].to_numpy() != candidate_block["shape_category"].to_numpy()))
    penalty = settings.sequence_weight_category * (mismatch_count / len(target_block))
    return float(penalty), mismatch_count


def calc_pair_sequence_penalty(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> tuple[float, int]:
    t_dir = target_block["direction"].to_numpy()
    c_dir = candidate_block["direction"].to_numpy()
    t_cat = target_block["shape_category"].to_numpy()
    c_cat = candidate_block["shape_category"].to_numpy()

    mismatch_count = 0
    for i in range(len(target_block) - 1):
        if (t_dir[i], t_dir[i + 1], t_cat[i], t_cat[i + 1]) != (c_dir[i], c_dir[i + 1], c_cat[i], c_cat[i + 1]):
            mismatch_count += 1

    denom = max(1, len(target_block) - 1)
    penalty = settings.sequence_weight_pair * (mismatch_count / denom)
    return float(penalty), mismatch_count


def _aggregate_stats(block: pd.DataFrame) -> Dict[str, float]:
    dirs = block["direction"].to_numpy()
    return {
        "average_body_ratio": float(block["body_ratio"].mean()),
        "average_upper_wick_ratio": float(block["upper_wick_ratio"].mean()),
        "average_lower_wick_ratio": float(block["lower_wick_ratio"].mean()),
        "average_ma_gap_ratio": float(block["ma_gap_ratio"].mean()),
        "bullish_count": float(np.sum(dirs == 1)),
        "bearish_count": float(np.sum(dirs == -1)),
        "neutral_count": float(np.sum(dirs == 0)),
    }


def calc_aggregate_penalty(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> tuple[float, Dict[str, float]]:
    """Score whole-block aggregate similarity."""

    t = _aggregate_stats(target_block)
    c = _aggregate_stats(candidate_block)
    n = max(1, len(target_block))

    penalty = (
        settings.aggregate_weight_body * abs(t["average_body_ratio"] - c["average_body_ratio"])
        + settings.aggregate_weight_upper * abs(t["average_upper_wick_ratio"] - c["average_upper_wick_ratio"])
        + settings.aggregate_weight_lower * abs(t["average_lower_wick_ratio"] - c["average_lower_wick_ratio"])
        + settings.aggregate_weight_bullish * abs(t["bullish_count"] - c["bullish_count"]) / n
        + settings.aggregate_weight_bearish * abs(t["bearish_count"] - c["bearish_count"]) / n
        + settings.aggregate_weight_ma_gap * abs(t["average_ma_gap_ratio"] - c["average_ma_gap_ratio"])
    )

    return float(penalty), c


def score_candle_shape_v2(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> Dict[str, float]:
    """Return full score breakdown for candle_shape_v2."""

    base_shape_score = calc_base_shape_score(target_block, candidate_block, settings)
    direction_sequence_penalty, direction_mismatch_count = calc_direction_sequence_penalty(
        target_block, candidate_block, settings
    )
    shape_category_penalty, category_mismatch_count = calc_category_sequence_penalty(
        target_block, candidate_block, settings
    )
    pair_sequence_penalty, pair_mismatch_count = calc_pair_sequence_penalty(
        target_block, candidate_block, settings
    )
    aggregate_penalty, candidate_agg = calc_aggregate_penalty(target_block, candidate_block, settings)

    final_score = (
        base_shape_score
        + direction_sequence_penalty
        + shape_category_penalty
        + pair_sequence_penalty
        + aggregate_penalty
    )

    return {
        "final_score": float(final_score),
        "base_shape_score": float(base_shape_score),
        "direction_sequence_penalty": float(direction_sequence_penalty),
        "shape_category_penalty": float(shape_category_penalty),
        "pair_sequence_penalty": float(pair_sequence_penalty),
        "aggregate_penalty": float(aggregate_penalty),
        "direction_mismatch_count": float(direction_mismatch_count),
        "category_mismatch_count": float(category_mismatch_count),
        "pair_mismatch_count": float(pair_mismatch_count),
        **candidate_agg,
    }


def _find_close_pattern_v1(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    pattern_length = settings.pattern_length
    future_length = settings.future_length

    target_start = len(df) - pattern_length
    target_end = len(df) - 1

    target_norm = normalize_series(df["close"].iloc[target_start : target_end + 1])
    target_gap = float(df["gap"].iloc[target_start])

    max_candidate_start = len(df) - settings.exclude_recent_bars - pattern_length - future_length
    candidates: List[CandidateMatch] = []

    for start_idx in range(0, max_candidate_start + 1):
        end_idx = start_idx + pattern_length - 1
        future_idx = end_idx + future_length

        candidate_norm = normalize_series(df["close"].iloc[start_idx : end_idx + 1])
        shape_distance = float(np.sum((target_norm - candidate_norm) ** 2))

        candidate_gap = float(df["gap"].iloc[start_idx])
        if np.isnan(candidate_gap):
            continue

        score = shape_distance + settings.gap_weight * abs(target_gap - candidate_gap)
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
                score=float(score),
                candidate_gap=candidate_gap,
                future_return=float(future_return),
                logic_type="close_pattern_v1",
                score_breakdown={"final_score": float(score), "shape_distance": float(shape_distance)},
            )
        )

    return candidates


def _find_candle_shape_v2(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    pl = settings.candle_pattern_length
    future_length = settings.future_length

    feat_df = build_candle_features(df, settings.ma_window)
    feat_df = feat_df.dropna(subset=["ma_gap_ratio"]).copy()
    feat_df["shape_category"] = feat_df.apply(lambda r: classify_candle_shape(r, settings), axis=1)

    if len(feat_df) < pl + future_length + settings.exclude_recent_bars:
        raise ValueError("Not enough rows for candle_shape_v2. Increase data or reduce parameters.")

    target_start = len(feat_df) - pl
    target_end = len(feat_df) - 1
    target_block = feat_df.iloc[target_start : target_end + 1].reset_index(drop=True)

    max_candidate_start = len(feat_df) - settings.exclude_recent_bars - pl - future_length
    candidates: List[CandidateMatch] = []

    for start_idx in range(0, max_candidate_start + 1):
        end_idx = start_idx + pl - 1
        future_idx = end_idx + future_length

        candidate_block = feat_df.iloc[start_idx : end_idx + 1].reset_index(drop=True)
        score_detail = score_candle_shape_v2(target_block, candidate_block, settings)

        end_close = float(feat_df["close"].iloc[end_idx])
        future_close = float(feat_df["close"].iloc[future_idx])
        if np.isclose(end_close, 0.0):
            continue

        future_return = (future_close / end_close) - 1.0
        candidate_gap = float(feat_df["ma_gap_ratio"].iloc[start_idx])

        summary_stats = {
            "average_body_ratio": score_detail["average_body_ratio"],
            "average_upper_wick_ratio": score_detail["average_upper_wick_ratio"],
            "average_lower_wick_ratio": score_detail["average_lower_wick_ratio"],
            "average_ma_gap_ratio": score_detail["average_ma_gap_ratio"],
            "bullish_count": score_detail["bullish_count"],
            "bearish_count": score_detail["bearish_count"],
            "neutral_count": score_detail["neutral_count"],
            "direction_mismatch_count": score_detail["direction_mismatch_count"],
            "category_mismatch_count": score_detail["category_mismatch_count"],
            "pair_mismatch_count": score_detail["pair_mismatch_count"],
        }

        candidates.append(
            CandidateMatch(
                rank=0,
                start_idx=start_idx,
                end_idx=end_idx,
                candidate_start_datetime=feat_df["datetime"].iloc[start_idx],
                score=float(score_detail["final_score"]),
                candidate_gap=candidate_gap,
                future_return=float(future_return),
                logic_type="candle_shape_v2",
                score_breakdown=score_detail,
                summary_stats=summary_stats,
            )
        )

    return candidates


def find_similar_patterns(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    """Dispatcher for multiple similarity logic types."""

    required_cols = {"datetime", "open", "high", "low", "close", "gap"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Input DataFrame missing columns: {missing}")

    if settings.logic_type == "close_pattern_v1":
        candidates = _find_close_pattern_v1(df, settings)
    elif settings.logic_type == "candle_shape_v2":
        candidates = _find_candle_shape_v2(df, settings)
    else:
        raise ValueError(f"Unsupported logic_type: {settings.logic_type}")

    if not candidates:
        raise ValueError("No valid candidates were found.")

    top = sorted(candidates, key=lambda x: x.score)[: settings.top_k]
    for i, c in enumerate(top, start=1):
        c.rank = i
    return top
