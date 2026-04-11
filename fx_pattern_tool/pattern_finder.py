"""Pattern feature engineering and similarity search logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import pandas as pd

from config import Settings, validate_logic_type


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
    arr = series.astype(float).to_numpy()
    if len(arr) == 0:
        return arr
    base = arr[0]
    if np.isclose(base, 0.0):
        return arr - base
    return (arr / base) - 1.0


def add_features(df: pd.DataFrame, ma_window: int) -> pd.DataFrame:
    out = df.copy()
    out["ma"] = out["close"].rolling(ma_window).mean()
    out["gap"] = (out["close"] - out["ma"]) / out["ma"]
    return out


def _make_future_return(df: pd.DataFrame, end_idx: int, future_length: int) -> float:
    future_idx = end_idx + future_length
    end_close = float(df["close"].iloc[end_idx])
    future_close = float(df["close"].iloc[future_idx])
    if np.isclose(end_close, 0.0):
        return np.nan
    return float((future_close / end_close) - 1.0)


# =========================
# close_pattern_v1
# =========================
def find_similar_patterns_close(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    pattern_length = settings.pattern_length
    target_start = len(df) - pattern_length
    target_end = len(df) - 1

    target_norm = normalize_series(df["close"].iloc[target_start : target_end + 1])
    target_gap = float(df["gap"].iloc[target_start])

    max_candidate_start = len(df) - settings.exclude_recent_bars - pattern_length - settings.future_length
    candidates: List[CandidateMatch] = []

    for start_idx in range(0, max_candidate_start + 1):
        end_idx = start_idx + pattern_length - 1
        candidate_norm = normalize_series(df["close"].iloc[start_idx : end_idx + 1])
        shape_distance = float(np.sum((target_norm - candidate_norm) ** 2))

        candidate_gap = float(df["gap"].iloc[start_idx])
        if np.isnan(candidate_gap):
            continue

        score = shape_distance + settings.gap_weight * abs(target_gap - candidate_gap)
        future_return = _make_future_return(df, end_idx, settings.future_length)
        if np.isnan(future_return):
            continue

        candidates.append(
            CandidateMatch(
                rank=0,
                start_idx=start_idx,
                end_idx=end_idx,
                candidate_start_datetime=df["datetime"].iloc[start_idx],
                score=float(score),
                candidate_gap=candidate_gap,
                future_return=future_return,
                logic_type="close_pattern_v1",
                score_breakdown={"final_score": float(score), "shape_distance": float(shape_distance)},
            )
        )

    return candidates


# =========================
# candle_shape_v2
# =========================
def build_candle_features(df: pd.DataFrame, ma_window: int) -> pd.DataFrame:
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
    direction_penalty = (target_block["direction"].to_numpy() != candidate_block["direction"].to_numpy()).astype(float)
    return float(
        settings.candle_weight_ma_gap * np.sum((target_block["ma_gap_ratio"] - candidate_block["ma_gap_ratio"]) ** 2)
        + settings.candle_weight_upper_wick * np.sum((target_block["upper_wick_ratio"] - candidate_block["upper_wick_ratio"]) ** 2)
        + settings.candle_weight_lower_wick * np.sum((target_block["lower_wick_ratio"] - candidate_block["lower_wick_ratio"]) ** 2)
        + settings.candle_weight_body * np.sum((target_block["body_ratio"] - candidate_block["body_ratio"]) ** 2)
        + settings.candle_weight_direction * np.sum(direction_penalty)
    )


def calc_direction_sequence_penalty(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> tuple[float, int]:
    mismatch_count = int(np.sum(target_block["direction"].to_numpy() != candidate_block["direction"].to_numpy()))
    return float(settings.sequence_weight_direction * (mismatch_count / len(target_block))), mismatch_count


def calc_category_sequence_penalty(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> tuple[float, int]:
    mismatch_count = int(np.sum(target_block["shape_category"].to_numpy() != candidate_block["shape_category"].to_numpy()))
    return float(settings.sequence_weight_category * (mismatch_count / len(target_block))), mismatch_count


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
    return float(settings.sequence_weight_pair * (mismatch_count / denom)), mismatch_count


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
    base_shape_score = calc_base_shape_score(target_block, candidate_block, settings)
    direction_sequence_penalty, direction_mismatch_count = calc_direction_sequence_penalty(target_block, candidate_block, settings)
    shape_category_penalty, category_mismatch_count = calc_category_sequence_penalty(target_block, candidate_block, settings)
    pair_sequence_penalty, pair_mismatch_count = calc_pair_sequence_penalty(target_block, candidate_block, settings)
    aggregate_penalty, candidate_agg = calc_aggregate_penalty(target_block, candidate_block, settings)

    final_score = base_shape_score + direction_sequence_penalty + shape_category_penalty + pair_sequence_penalty + aggregate_penalty

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


def find_similar_patterns_candle(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    pl = settings.candle_pattern_length
    feat_df = build_candle_features(df, settings.ma_window)
    feat_df = feat_df.dropna(subset=["ma_gap_ratio"]).copy()
    feat_df["shape_category"] = feat_df.apply(lambda r: classify_candle_shape(r, settings), axis=1)

    target_start = len(feat_df) - pl
    target_end = len(feat_df) - 1
    target_block = feat_df.iloc[target_start : target_end + 1].reset_index(drop=True)

    max_candidate_start = len(feat_df) - settings.exclude_recent_bars - pl - settings.future_length
    candidates: List[CandidateMatch] = []

    for start_idx in range(0, max_candidate_start + 1):
        end_idx = start_idx + pl - 1
        candidate_block = feat_df.iloc[start_idx : end_idx + 1].reset_index(drop=True)
        score_detail = score_candle_shape_v2(target_block, candidate_block, settings)
        future_return = _make_future_return(feat_df, end_idx, settings.future_length)
        if np.isnan(future_return):
            continue

        candidates.append(
            CandidateMatch(
                rank=0,
                start_idx=start_idx,
                end_idx=end_idx,
                candidate_start_datetime=feat_df["datetime"].iloc[start_idx],
                score=float(score_detail["final_score"]),
                candidate_gap=float(feat_df["ma_gap_ratio"].iloc[start_idx]),
                future_return=future_return,
                logic_type="candle_shape_v2",
                score_breakdown=score_detail,
                summary_stats={
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
                },
            )
        )

    return candidates


# =========================
# ma_gap_structure_v1
# =========================
def _build_ma_gap_structure_features(df: pd.DataFrame, ma_window: int) -> pd.DataFrame:
    out = df.copy()
    out["sma"] = out["close"].rolling(ma_window).mean()
    out["ema"] = out["close"].ewm(span=ma_window, adjust=False).mean()
    out["ema_sma_gap_pct"] = ((out["ema"] - out["sma"]) / out["sma"]).replace([np.inf, -np.inf], np.nan)
    out["close_ema_gap_pct"] = ((out["close"] - out["ema"]) / out["ema"]).replace([np.inf, -np.inf], np.nan)
    out["ema_sma_sign"] = np.sign(out["ema_sma_gap_pct"].fillna(0.0))
    out["close_ema_sign"] = np.sign(out["close_ema_gap_pct"].fillna(0.0))
    return out


def _score_ma_gap_structure_v1(target_block: pd.DataFrame, candidate_block: pd.DataFrame, settings: Settings) -> Dict[str, float]:
    ema_sma_diff = target_block["ema_sma_gap_pct"].to_numpy() - candidate_block["ema_sma_gap_pct"].to_numpy()
    close_ema_diff = target_block["close_ema_gap_pct"].to_numpy() - candidate_block["close_ema_gap_pct"].to_numpy()

    shape_score = (
        settings.ma_gap_weight_ema_sma * float(np.sum(ema_sma_diff**2))
        + settings.ma_gap_weight_close_ema * float(np.sum(close_ema_diff**2))
    )

    ema_sma_sign_mismatch = int(np.sum(target_block["ema_sma_sign"].to_numpy() != candidate_block["ema_sma_sign"].to_numpy()))
    close_ema_sign_mismatch = int(np.sum(target_block["close_ema_sign"].to_numpy() != candidate_block["close_ema_sign"].to_numpy()))

    sign_penalty = (
        settings.ma_gap_sign_penalty_ema_sma * (ema_sma_sign_mismatch / len(target_block))
        + settings.ma_gap_sign_penalty_close_ema * (close_ema_sign_mismatch / len(target_block))
    )

    target_agg_ema_sma = float(target_block["ema_sma_gap_pct"].mean())
    target_agg_close_ema = float(target_block["close_ema_gap_pct"].mean())
    candidate_agg_ema_sma = float(candidate_block["ema_sma_gap_pct"].mean())
    candidate_agg_close_ema = float(candidate_block["close_ema_gap_pct"].mean())

    aggregate_penalty = (
        settings.ma_gap_aggregate_weight_ema_sma * abs(target_agg_ema_sma - candidate_agg_ema_sma)
        + settings.ma_gap_aggregate_weight_close_ema * abs(target_agg_close_ema - candidate_agg_close_ema)
    )

    final_score = shape_score + sign_penalty + aggregate_penalty
    sign_match_ratio = 1.0 - ((ema_sma_sign_mismatch + close_ema_sign_mismatch) / (2 * len(target_block)))

    return {
        "final_score": float(final_score),
        "shape_score": float(shape_score),
        "sign_penalty": float(sign_penalty),
        "aggregate_penalty": float(aggregate_penalty),
        "average_ema_sma_gap_pct": candidate_agg_ema_sma,
        "average_close_ema_gap_pct": candidate_agg_close_ema,
        "ema_sma_sign_mismatch_count": float(ema_sma_sign_mismatch),
        "close_ema_sign_mismatch_count": float(close_ema_sign_mismatch),
        "sign_match_ratio": float(sign_match_ratio),
    }


def find_similar_patterns_ma_gap(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    pl = settings.ma_gap_pattern_length
    feat_df = _build_ma_gap_structure_features(df, settings.ma_window)
    feat_df = feat_df.dropna(subset=["ema_sma_gap_pct", "close_ema_gap_pct"]).copy()

    target_start = len(feat_df) - pl
    target_end = len(feat_df) - 1
    target_block = feat_df.iloc[target_start : target_end + 1].reset_index(drop=True)

    max_candidate_start = len(feat_df) - settings.exclude_recent_bars - pl - settings.future_length
    candidates: List[CandidateMatch] = []

    for start_idx in range(0, max_candidate_start + 1):
        end_idx = start_idx + pl - 1
        candidate_block = feat_df.iloc[start_idx : end_idx + 1].reset_index(drop=True)
        detail = _score_ma_gap_structure_v1(target_block, candidate_block, settings)
        future_return = _make_future_return(feat_df, end_idx, settings.future_length)
        if np.isnan(future_return):
            continue

        candidates.append(
            CandidateMatch(
                rank=0,
                start_idx=start_idx,
                end_idx=end_idx,
                candidate_start_datetime=feat_df["datetime"].iloc[start_idx],
                score=float(detail["final_score"]),
                candidate_gap=float(feat_df["close_ema_gap_pct"].iloc[start_idx]),
                future_return=future_return,
                logic_type="ma_gap_structure_v1",
                score_breakdown=detail,
                summary_stats={
                    "average_ema_sma_gap_pct": detail["average_ema_sma_gap_pct"],
                    "average_close_ema_gap_pct": detail["average_close_ema_gap_pct"],
                    "sign_match_ratio": detail["sign_match_ratio"],
                    "ema_sma_sign_mismatch_count": detail["ema_sma_sign_mismatch_count"],
                    "close_ema_sign_mismatch_count": detail["close_ema_sign_mismatch_count"],
                },
            )
        )

    return candidates




# =========================
# env_mask_zscore_v4
# =========================
def find_similar_patterns_env_mask_v4(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    """Logic4: strict regime mask + vectorized z-score Euclidean search."""

    window = settings.env_window_size
    horizon = settings.env_forecast_horizon
    n = len(df)

    if n < settings.ma_window + window + horizon + settings.exclude_recent_bars:
        raise ValueError("Not enough rows for env_mask_zscore_v4.")

    work = df.copy()
    work["ma200"] = work["close"].rolling(settings.ma_window).mean()
    work["ma_slope"] = work["ma200"].diff()

    valid_mask = (~work["ma200"].isna()) & (~work["ma_slope"].isna())
    valid_idx = np.where(valid_mask.to_numpy())[0]
    if len(valid_idx) <= window + horizon:
        raise ValueError("Insufficient valid MA rows for env logic.")

    close = work["close"].to_numpy(dtype=float)
    ma = work["ma200"].to_numpy(dtype=float)
    slope = work["ma_slope"].to_numpy(dtype=float)

    current_up = slope[-1] > 0
    current_above = close[-1] > ma[-1]

    windows = sliding_window_view(close, window_shape=window)
    means = windows.mean(axis=1, keepdims=True)
    stds = windows.std(axis=1, keepdims=True)
    stds = np.where(stds == 0, 1.0, stds)
    z_windows = (windows - means) / stds

    target_vec = z_windows[-1]
    dists = np.sqrt(np.sum((z_windows - target_vec) ** 2, axis=1))

    starts = np.arange(z_windows.shape[0])
    ends = starts + window - 1

    regime_mask = ((slope[ends] > 0) == current_up) & ((close[ends] > ma[ends]) == current_above)
    enough_future = (ends + horizon) < n
    not_recent = starts <= (n - window - horizon - settings.exclude_recent_bars)
    valid = regime_mask & enough_future & not_recent

    if not np.any(valid):
        raise ValueError("No candidates passed strict environment mask.")

    masked_dists = np.where(valid, dists, np.inf)
    top_k = min(settings.top_k, int(np.sum(np.isfinite(masked_dists))))
    best_idx = np.argpartition(masked_dists, top_k - 1)[:top_k]
    best_idx = best_idx[np.argsort(masked_dists[best_idx])]

    candidates: List[CandidateMatch] = []
    current_price = close[-1]
    for rank_i, start_idx in enumerate(best_idx, start=1):
        end_idx = int(start_idx + window - 1)
        future_close = close[end_idx : end_idx + horizon + 1]
        pct_path = (future_close / future_close[0]) - 1.0
        predicted_price_end = float(current_price * (1.0 + pct_path[-1]))

        candidates.append(
            CandidateMatch(
                rank=rank_i,
                start_idx=int(start_idx),
                end_idx=end_idx,
                candidate_start_datetime=work["datetime"].iloc[start_idx],
                score=float(masked_dists[start_idx]),
                candidate_gap=float((close[end_idx] - ma[end_idx]) / ma[end_idx]) if ma[end_idx] != 0 else 0.0,
                future_return=float((close[end_idx + horizon] / close[end_idx]) - 1.0),
                logic_type="env_mask_zscore_v4",
                score_breakdown={
                    "final_score": float(masked_dists[start_idx]),
                    "z_euclidean": float(masked_dists[start_idx]),
                },
                summary_stats={
                    "env_ma_slope_up": float(1 if current_up else 0),
                    "env_price_above_ma": float(1 if current_above else 0),
                    "predicted_price_after_20": predicted_price_end,
                    "predicted_return_after_20": float(pct_path[-1]),
                },
            )
        )

    return candidates

def find_similar_patterns(df: pd.DataFrame, settings: Settings) -> List[CandidateMatch]:
    """Common entrypoint that dispatches by settings.logic_type."""

    validate_logic_type(settings.logic_type)

    required_cols = {"datetime", "open", "high", "low", "close", "gap"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Input DataFrame missing columns: {missing}")

    if settings.logic_type == "close_pattern_v1":
        candidates = find_similar_patterns_close(df, settings)
    elif settings.logic_type == "candle_shape_v2":
        candidates = find_similar_patterns_candle(df, settings)
    elif settings.logic_type == "ma_gap_structure_v1":
        candidates = find_similar_patterns_ma_gap(df, settings)
    elif settings.logic_type == "env_mask_zscore_v4":
        candidates = find_similar_patterns_env_mask_v4(df, settings)
    else:
        # validate_logic_type() already guards this, but keep explicit branch for readability
        raise ValueError(f"Unsupported logic_type: {settings.logic_type}")

    if not candidates:
        raise ValueError(
            f"No valid candidates were found for logic_type={settings.logic_type}. "
            "Increase data amount or reduce constraints."
        )

    top = sorted(candidates, key=lambda x: x.score)[: settings.top_k]
    for i, c in enumerate(top, start=1):
        c.rank = i
    return top
