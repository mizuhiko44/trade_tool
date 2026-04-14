"""Rule-based chart pattern classifier for latest candles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd


DIRECTION_MEANING_DEFAULTS: Dict[str, str] = {
    "上向き": "上昇しやすい、または上昇継続に近い形です",
    "下向き": "下落しやすい、または下降継続に近い形です",
    "迷っている": "まだ方向感がはっきりせず、上下どちらにも動きうる形です",
}


@dataclass(frozen=True)
class PatternDefinition:
    pattern_name_internal: str
    pattern_name_display: str
    direction_label: str
    direction_meaning: str
    explanation_short: str
    profile: Dict[str, float]
    boosts: List[tuple[str, float, float, float]]
    penalties: List[tuple[str, float, float, float]]


def _safe_div(num: float, den: float) -> float:
    if np.isclose(den, 0.0):
        return 0.0
    return float(num / den)


def _longest_run(direction: np.ndarray, target: int) -> int:
    longest = 0
    current = 0
    for d in direction:
        if d == target:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _linear_slope(values: np.ndarray) -> float:
    if len(values) <= 1:
        return 0.0
    x = np.arange(len(values), dtype=float)
    slope = np.polyfit(x, values.astype(float), 1)[0]
    return float(slope)


def build_recent_candle_features(df: pd.DataFrame, lookback: int = 10) -> Dict[str, Any]:
    if lookback <= 1:
        raise ValueError("lookback must be >= 2")
    required_cols = {"open", "high", "low", "close"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")

    frame = df.tail(lookback).copy().reset_index(drop=True)
    if len(frame) < lookback:
        raise ValueError(f"Not enough bars for lookback={lookback}. got={len(frame)}")

    frame["body"] = (frame["close"] - frame["open"]).abs()
    frame["range"] = frame["high"] - frame["low"]
    frame["upper_wick"] = frame["high"] - frame[["open", "close"]].max(axis=1)
    frame["lower_wick"] = frame[["open", "close"]].min(axis=1) - frame["low"]

    safe_range = frame["range"].replace(0, np.nan)
    frame["body_ratio"] = (frame["body"] / safe_range).fillna(0.0)
    frame["upper_wick_ratio"] = (frame["upper_wick"] / safe_range).fillna(0.0)
    frame["lower_wick_ratio"] = (frame["lower_wick"] / safe_range).fillna(0.0)
    frame["direction"] = np.where(frame["close"] > frame["open"], 1, np.where(frame["close"] < frame["open"], -1, 0))

    direction_arr = frame["direction"].to_numpy()
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    ranges = frame["range"].to_numpy(dtype=float)

    bullish_count = int(np.sum(direction_arr == 1))
    bearish_count = int(np.sum(direction_arr == -1))
    neutral_count = int(np.sum(direction_arr == 0))

    hh = int(np.sum(np.diff(highs) > 0))
    hl = int(np.sum(np.diff(lows) > 0))
    lh = int(np.sum(np.diff(highs) < 0))
    ll = int(np.sum(np.diff(lows) < 0))

    close_slope_raw = _linear_slope(closes)
    high_slope_raw = _linear_slope(highs)
    low_slope_raw = _linear_slope(lows)
    close_base = max(abs(closes[0]), 1e-9)
    high_base = max(abs(highs[0]), 1e-9)
    low_base = max(abs(lows[0]), 1e-9)

    close_slope = float(close_slope_raw / close_base)
    high_slope = float(high_slope_raw / high_base)
    low_slope = float(low_slope_raw / low_base)

    half = max(1, lookback // 2)
    first_half = frame.iloc[:half]
    second_half = frame.iloc[half:]
    last3 = frame.iloc[-3:]

    trend_up_strength = float(np.clip((max(close_slope, 0) * 250) + (hh + hl) / (2 * max(1, lookback - 1)), 0.0, 1.0))
    trend_down_strength = float(np.clip((max(-close_slope, 0) * 250) + (lh + ll) / (2 * max(1, lookback - 1)), 0.0, 1.0))

    avg_range = float(np.mean(ranges))
    min_range = float(np.min(ranges))
    max_range = float(np.max(ranges))
    close_std = float(np.std(closes))
    range_std = float(np.std(ranges))

    ma_window = min(max(lookback * 3, 20), max(len(df), 20))
    long_ma_series = df["close"].rolling(ma_window).mean()
    recent_ma = long_ma_series.tail(lookback).reset_index(drop=True)
    ma_valid = recent_ma.notna().all()
    if ma_valid:
        ma_vals = recent_ma.to_numpy(dtype=float)
        above_long_ma_ratio = float(np.mean(closes > ma_vals))
        below_long_ma_ratio = float(np.mean(closes < ma_vals))
        long_ma_distance = float(np.mean((closes - ma_vals) / np.maximum(np.abs(ma_vals), 1e-9)))
    else:
        above_long_ma_ratio = 0.0
        below_long_ma_ratio = 0.0
        long_ma_distance = 0.0

    features: Dict[str, Any] = {
        "lookback": lookback,
        "candles": frame,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "avg_body_ratio": float(frame["body_ratio"].mean()),
        "avg_upper_wick_ratio": float(frame["upper_wick_ratio"].mean()),
        "avg_lower_wick_ratio": float(frame["lower_wick_ratio"].mean()),
        "avg_range": avg_range,
        "max_range": max_range,
        "min_range": min_range,
        "close_slope": close_slope,
        "high_slope": high_slope,
        "low_slope": low_slope,
        "close_std": close_std,
        "range_std": range_std,
        "higher_high_count": hh,
        "higher_low_count": hl,
        "lower_high_count": lh,
        "lower_low_count": ll,
        "longest_bullish_run": _longest_run(direction_arr, 1),
        "longest_bearish_run": _longest_run(direction_arr, -1),
        "bullish_ratio": bullish_count / lookback,
        "bearish_ratio": bearish_count / lookback,
        "neutral_ratio": neutral_count / lookback,
        "mixed_ratio": 1.0 - abs((bullish_count - bearish_count) / lookback),
        "trend_up_strength": trend_up_strength,
        "trend_down_strength": trend_down_strength,
        "higher_high_ratio": _safe_div(hh, lookback - 1),
        "higher_low_ratio": _safe_div(hl, lookback - 1),
        "lower_high_ratio": _safe_div(lh, lookback - 1),
        "lower_low_ratio": _safe_div(ll, lookback - 1),
        "longest_bullish_run_ratio": _safe_div(_longest_run(direction_arr, 1), lookback),
        "longest_bearish_run_ratio": _safe_div(_longest_run(direction_arr, -1), lookback),
        "small_body_ratio": float(np.mean(frame["body_ratio"] <= 0.22)),
        "large_body_ratio": float(np.mean(frame["body_ratio"] >= 0.58)),
        "upper_long_wick_ratio": float(np.mean(frame["upper_wick_ratio"] >= 0.45)),
        "lower_long_wick_ratio": float(np.mean(frame["lower_wick_ratio"] >= 0.45)),
        "wick_balance": float(1.0 - min(1.0, abs(frame["upper_wick_ratio"].mean() - frame["lower_wick_ratio"].mean()))),
        "range_compression": float(np.clip(1.0 - _safe_div(range_std, avg_range + 1e-9), 0.0, 1.0)),
        "range_expansion": float(np.clip(_safe_div(max_range, min_range + 1e-9) / 4.0, 0.0, 1.0)),
        "volatility_compression": float(np.clip(1.0 - _safe_div(close_std, abs(closes.mean()) * 0.02 + 1e-9), 0.0, 1.0)),
        "volatility_expansion": float(np.clip(_safe_div(close_std, abs(closes.mean()) * 0.02 + 1e-9), 0.0, 1.0)),
        "first_half_up_ratio": float(np.mean(first_half["direction"] == 1)),
        "first_half_down_ratio": float(np.mean(first_half["direction"] == -1)),
        "second_half_up_ratio": float(np.mean(second_half["direction"] == 1)) if len(second_half) else 0.0,
        "second_half_down_ratio": float(np.mean(second_half["direction"] == -1)) if len(second_half) else 0.0,
        "recent_up_ratio": float(np.mean(last3["direction"] == 1)),
        "recent_down_ratio": float(np.mean(last3["direction"] == -1)),
        "above_long_ma_ratio": above_long_ma_ratio,
        "below_long_ma_ratio": below_long_ma_ratio,
        "long_ma_distance": long_ma_distance,
    }
    return features


def _make_pattern(
    internal: str,
    display: str,
    direction: str,
    meaning: str,
    explanation: str,
    profile: Dict[str, float],
    boosts: List[tuple[str, float, float, float]] | None = None,
    penalties: List[tuple[str, float, float, float]] | None = None,
) -> PatternDefinition:
    return PatternDefinition(
        pattern_name_internal=internal,
        pattern_name_display=display,
        direction_label=direction,
        direction_meaning=meaning or DIRECTION_MEANING_DEFAULTS[direction],
        explanation_short=explanation,
        profile=profile,
        boosts=boosts or [],
        penalties=penalties or [],
    )


def get_pattern_definitions() -> List[Dict[str, Any]]:
    patterns = [
        _make_pattern("uptrend_strong", "強い上昇トレンド", "上向き", "買い優勢で、高値と安値を切り上げながら上に進みやすい形です", "高値・安値の切り上げと陽線優勢が同時に出ています", {"trend_up_strength": 0.95, "bullish_ratio": 0.8, "higher_high_ratio": 0.8, "higher_low_ratio": 0.75}),
        _make_pattern("uptrend_mild", "緩やかな上昇トレンド", "上向き", "上昇バイアスはあるものの、勢いは穏やかな状態です", "上昇基調ですが、勢いは強すぎない推移です", {"trend_up_strength": 0.7, "bullish_ratio": 0.6, "higher_high_ratio": 0.6, "higher_low_ratio": 0.6}),
        _make_pattern("downtrend_strong", "強い下降トレンド", "下向き", "売り優勢で、高値と安値を切り下げながら下に進みやすい形です", "高値・安値の切り下げが明確な下降基調です", {"trend_down_strength": 0.95, "bearish_ratio": 0.8, "lower_high_ratio": 0.8, "lower_low_ratio": 0.75}),
        _make_pattern("downtrend_mild", "緩やかな下降トレンド", "下向き", "下降バイアスはあるものの、売り圧力は極端ではない状態です", "緩やかに下方向へ値位置が切り下がっています", {"trend_down_strength": 0.7, "bearish_ratio": 0.6, "lower_high_ratio": 0.6, "lower_low_ratio": 0.6}),
        _make_pattern("sideways_range", "レンジ相場", "迷っている", "方向感がまだ弱く、上下どちらにも抜ける可能性がある形です", "上下の偏りが少なく、持ち合いに近いです", {"mixed_ratio": 0.95, "trend_up_strength": 0.3, "trend_down_strength": 0.3, "range_compression": 0.6}),
        _make_pattern("squeeze_range", "収縮レンジ", "迷っている", "値幅が絞られており、次のブレイク待ちになりやすい形です", "値幅の縮小が進む収縮局面です", {"range_compression": 0.95, "volatility_compression": 0.9, "mixed_ratio": 0.85}),
        _make_pattern("expansion_breakout_up", "上放れ拡大型", "上向き", "上方向に値幅拡大しやすく、上抜け継続が起きやすい形です", "上方向への拡大と陽線優勢が組み合わさっています", {"volatility_expansion": 0.9, "trend_up_strength": 0.85, "recent_up_ratio": 0.8}),
        _make_pattern("expansion_breakout_down", "下放れ拡大型", "下向き", "下方向に値幅拡大しやすく、下抜け継続が起きやすい形です", "下方向への拡大と陰線優勢が目立ちます", {"volatility_expansion": 0.9, "trend_down_strength": 0.85, "recent_down_ratio": 0.8}),
        _make_pattern("top_reversal_candidate", "天井反転候補", "下向き", "上昇の勢いが鈍り、反落へ転じやすい初期サインです", "上昇後に上ヒゲ・陰線が増えて失速感が見られます", {"first_half_up_ratio": 0.75, "second_half_down_ratio": 0.6, "upper_long_wick_ratio": 0.45}),
        _make_pattern("bottom_reversal_candidate", "底打ち反転候補", "上向き", "下落の勢いが弱まり、反発へ転じやすい初期サインです", "下落後に下ヒゲ・陽線が増えて反転の芽が見えます", {"first_half_down_ratio": 0.75, "second_half_up_ratio": 0.6, "lower_long_wick_ratio": 0.45}),
        _make_pattern("double_top_like", "ダブルトップ型", "下向き", "上値が重くなりやすく、反落に向かいやすい形です", "高値更新が続かず、上値抵抗を作っています", {"upper_long_wick_ratio": 0.5, "trend_up_strength": 0.55, "recent_down_ratio": 0.65}),
        _make_pattern("double_bottom_like", "ダブルボトム型", "上向き", "下値が支えられやすく、反発へ向かいやすい形です", "安値圏で下ヒゲが機能し、切り返しの形です", {"lower_long_wick_ratio": 0.5, "trend_down_strength": 0.55, "recent_up_ratio": 0.65}),
        _make_pattern("rounded_top_like", "丸天井型", "下向き", "上昇の勢いが徐々に減速し、下方向へ移りやすい形です", "緩やかな失速で天井圏の滞在が長い形です", {"first_half_up_ratio": 0.7, "second_half_down_ratio": 0.5, "small_body_ratio": 0.5}),
        _make_pattern("rounded_bottom_like", "丸底型", "上向き", "下落の勢いが徐々に減速し、上方向へ移りやすい形です", "底練りから徐々に買い優勢へ変化しています", {"first_half_down_ratio": 0.7, "second_half_up_ratio": 0.5, "small_body_ratio": 0.5}),
        _make_pattern("v_reversal_up", "V字反転上昇型", "上向き", "急落後に急反発し、短期的に上へ戻しやすい形です", "下落から素早く切り返すV字の戻りです", {"first_half_down_ratio": 0.85, "second_half_up_ratio": 0.85, "volatility_expansion": 0.7}),
        _make_pattern("v_reversal_down", "V字反転下降型", "下向き", "急騰後に急反落し、短期的に下へ戻しやすい形です", "上昇から素早く崩れる逆V字の失速です", {"first_half_up_ratio": 0.85, "second_half_down_ratio": 0.85, "volatility_expansion": 0.7}),
        _make_pattern("bullish_flag_like", "ブルフラッグ型", "上向き", "上昇後の短期調整を経て、再上昇しやすい形です", "上昇後に小幅な持ち合いが入る継続パターンです", {"trend_up_strength": 0.75, "second_half_down_ratio": 0.45, "range_compression": 0.75}),
        _make_pattern("bearish_flag_like", "ベアフラッグ型", "下向き", "下落後の短期戻しを経て、再下落しやすい形です", "下落後に小幅な持ち合いが入る継続パターンです", {"trend_down_strength": 0.75, "second_half_up_ratio": 0.45, "range_compression": 0.75}),
        _make_pattern("bullish_pullback", "上昇トレンド中の押し目", "上向き", "上昇基調の中の一時的な調整に近く、再び上に向かいやすい形です", "上昇地合いを維持したまま短期調整しています", {"trend_up_strength": 0.78, "recent_down_ratio": 0.5, "above_long_ma_ratio": 0.8}),
        _make_pattern("bearish_pullback", "下降トレンド中の戻り", "下向き", "下降基調の中の一時的な戻しに近く、再び下に向かいやすい形です", "下降地合いの中で戻りが入っている状態です", {"trend_down_strength": 0.78, "recent_up_ratio": 0.5, "below_long_ma_ratio": 0.8}),
        _make_pattern("ascending_like", "上昇継続型", "上向き", "押しを挟みながらも上方向への継続が意識される形です", "高値・安値をじり高で更新しています", {"higher_high_ratio": 0.75, "higher_low_ratio": 0.75, "bullish_ratio": 0.65}),
        _make_pattern("descending_like", "下降継続型", "下向き", "戻しを挟みながらも下方向への継続が意識される形です", "高値・安値をじり安で更新しています", {"lower_high_ratio": 0.75, "lower_low_ratio": 0.75, "bearish_ratio": 0.65}),
        _make_pattern("consecutive_bullish", "連続陽線型", "上向き", "買いの連続性が高く、上昇圧力が持続しやすい形です", "陽線の連続が目立ち、上方向の勢いがあります", {"longest_bullish_run_ratio": 0.7, "bullish_ratio": 0.8, "avg_body_ratio": 0.55}),
        _make_pattern("consecutive_bearish", "連続陰線型", "下向き", "売りの連続性が高く、下落圧力が持続しやすい形です", "陰線の連続が目立ち、下方向の勢いがあります", {"longest_bearish_run_ratio": 0.7, "bearish_ratio": 0.8, "avg_body_ratio": 0.55}),
        _make_pattern("mixed_indecision", "迷い相場型", "迷っている", "売り買いが拮抗し、方向の決め手が不足している形です", "陽線と陰線が混在しており方向性が薄いです", {"mixed_ratio": 0.95, "small_body_ratio": 0.6, "wick_balance": 0.8}),
        _make_pattern("bullish_with_long_lower_wicks", "下ヒゲ優勢の強気型", "上向き", "押し目で買い支えられやすく、上方向へ戻しやすい形です", "下ヒゲが優勢で下値の支えが確認できます", {"lower_long_wick_ratio": 0.75, "avg_lower_wick_ratio": 0.5, "trend_up_strength": 0.55}),
        _make_pattern("bearish_with_long_upper_wicks", "上ヒゲ優勢の弱気型", "下向き", "戻り売りに押されやすく、上値が重くなりやすい形です", "上ヒゲが優勢で上値の重さが目立ちます", {"upper_long_wick_ratio": 0.75, "avg_upper_wick_ratio": 0.5, "trend_down_strength": 0.55}),
        _make_pattern("small_body_cluster", "小実体集積型", "迷っている", "エネルギーをためる局面で、次の方向選択待ちの形です", "小さい実体が続き、様子見が強い状態です", {"small_body_ratio": 0.8, "mixed_ratio": 0.8, "range_compression": 0.7}),
        _make_pattern("large_body_expansion", "大実体拡大型", "迷っている", "大きな値幅の足が増え、相場が荒れやすい局面です", "大実体が増えて値動きが荒くなっています", {"large_body_ratio": 0.7, "volatility_expansion": 0.8, "range_expansion": 0.8}),
        _make_pattern("volatility_compression", "ボラティリティ収縮型", "迷っている", "値動きが細り、次の方向ブレイクを待つ状態です", "ボラティリティが低下し、値幅が締まっています", {"volatility_compression": 0.9, "range_compression": 0.85, "small_body_ratio": 0.6}),
        _make_pattern("volatility_expansion", "ボラティリティ拡大型", "迷っている", "値動きが拡大し、短期ノイズが増えやすい状態です", "直近の変動幅が広がっている局面です", {"volatility_expansion": 0.9, "range_expansion": 0.8, "large_body_ratio": 0.55}),
        _make_pattern("above_long_ma_stable", "長期線上安定型", "上向き", "長期移動平均線の上で推移し、上昇地合いを維持しやすい形です", "長期線より上で安定し、押しが浅い状態です", {"above_long_ma_ratio": 0.95, "trend_up_strength": 0.7, "range_compression": 0.65}),
        _make_pattern("below_long_ma_stable", "長期線下安定型", "下向き", "長期移動平均線の下で推移し、下降地合いを維持しやすい形です", "長期線より下で安定し、戻りが限定されています", {"below_long_ma_ratio": 0.95, "trend_down_strength": 0.7, "range_compression": 0.65}),
        _make_pattern("above_ma_pullback", "長期線上の押し目型", "上向き", "長期線の上での調整局面で、再上昇しやすい形です", "長期線上を維持したまま短期調整しています", {"above_long_ma_ratio": 0.85, "recent_down_ratio": 0.55, "trend_up_strength": 0.65}),
        _make_pattern("below_ma_rebound", "長期線下の戻り型", "下向き", "長期線の下での戻り局面で、再下落しやすい形です", "長期線下のまま一時反発している状態です", {"below_long_ma_ratio": 0.85, "recent_up_ratio": 0.55, "trend_down_strength": 0.65}),
        _make_pattern("upper_wick_exhaustion", "上ヒゲ失速型", "下向き", "上方向の試しが失敗しやすく、失速から反落しやすい形です", "上ヒゲが目立ち、上値追いの勢いが弱いです", {"avg_upper_wick_ratio": 0.55, "upper_long_wick_ratio": 0.7, "recent_down_ratio": 0.55}),
        _make_pattern("lower_wick_support", "下ヒゲ支持型", "上向き", "下方向の試しが吸収されやすく、反発しやすい形です", "下ヒゲが目立ち、下値支持が機能しています", {"avg_lower_wick_ratio": 0.55, "lower_long_wick_ratio": 0.7, "recent_up_ratio": 0.55}),
        _make_pattern("breakout_failed_up", "上抜け失敗型", "下向き", "上抜けが定着せず、反対方向へ戻されやすい形です", "上方向のブレイクが失敗し、押し戻されています", {"first_half_up_ratio": 0.7, "second_half_down_ratio": 0.75, "upper_long_wick_ratio": 0.5}),
        _make_pattern("breakout_failed_down", "下抜け失敗型", "上向き", "下抜けが定着せず、反対方向へ戻されやすい形です", "下方向のブレイクが失敗し、買い戻しが入っています", {"first_half_down_ratio": 0.7, "second_half_up_ratio": 0.75, "lower_long_wick_ratio": 0.5}),
        _make_pattern("narrow_box_range", "狭いボックス相場", "迷っている", "非常に狭いレンジ内で推移し、方向決定待ちの形です", "高値・安値の幅が狭く、横ばいが続いています", {"range_compression": 0.95, "mixed_ratio": 0.9, "volatility_compression": 0.9}),
    ]
    return [p.__dict__ for p in patterns]


def _score_one_pattern(pattern: Dict[str, Any], features: Dict[str, Any]) -> float:
    score = 45.0
    profile = pattern.get("profile", {})
    total_weight = max(1e-9, sum(abs(v) for v in profile.values()))
    fit = 0.0
    for key, target in profile.items():
        value = float(features.get(key, 0.0))
        distance = abs(value - float(target))
        fit += max(0.0, 1.0 - distance) * abs(target)
    score += 45.0 * (fit / total_weight)

    for key, low, high, points in pattern.get("boosts", []):
        val = float(features.get(key, 0.0))
        if low <= val <= high:
            score += points

    for key, low, high, points in pattern.get("penalties", []):
        val = float(features.get(key, 0.0))
        if low <= val <= high:
            score -= points

    return float(np.clip(score, 0.0, 100.0))


def classify_chart_pattern(df: pd.DataFrame, lookback: int = 10, top_n: int = 3) -> Dict[str, Any]:
    features = build_recent_candle_features(df, lookback=lookback)
    definitions = get_pattern_definitions()

    scored: List[Dict[str, Any]] = []
    for p in definitions:
        s = _score_one_pattern(p, features)
        scored.append(
            {
                "pattern_name_internal": p["pattern_name_internal"],
                "pattern_name_display": p["pattern_name_display"],
                "pattern_score": round(s, 2),
                "explanation_short": p["explanation_short"],
                "direction_label": p["direction_label"],
                "direction_meaning": p["direction_meaning"],
            }
        )

    scored.sort(key=lambda x: x["pattern_score"], reverse=True)
    top_n = max(1, int(top_n))
    best = scored[0]
    return {
        **best,
        "lookback": lookback,
        "top_patterns": scored[:top_n],
        "feature_snapshot": {
            "bullish_count": features["bullish_count"],
            "bearish_count": features["bearish_count"],
            "neutral_count": features["neutral_count"],
            "close_slope": round(features["close_slope"], 6),
            "higher_high_count": features["higher_high_count"],
            "higher_low_count": features["higher_low_count"],
            "lower_high_count": features["lower_high_count"],
            "lower_low_count": features["lower_low_count"],
            "range_std": round(features["range_std"], 6),
            "close_std": round(features["close_std"], 6),
        },
    }
