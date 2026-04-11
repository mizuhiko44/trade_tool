"""Plotly chart generation for current and candidate patterns."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import List

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import Settings
from pattern_finder import CandidateMatch


def _get_bar_delta(df: pd.DataFrame) -> timedelta:
    """Estimate one-bar time delta from datetime column."""

    dt = pd.to_datetime(df["datetime"])
    diffs = dt.diff().dropna()
    if diffs.empty:
        return timedelta(days=1)
    median = diffs.median()
    if pd.isna(median) or median <= pd.Timedelta(0):
        return timedelta(days=1)
    return median.to_pytimedelta()


def _add_candles_and_ma(
    fig: go.Figure,
    row: int,
    col: int,
    frame: pd.DataFrame,
    title: str,
) -> None:
    """Add a single candlestick + MA panel into subplot figure."""

    fig.add_trace(
        go.Candlestick(
            x=frame["datetime"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name=f"OHLC-{row}",
            showlegend=False,
        ),
        row=row,
        col=col,
    )

    fig.add_trace(
        go.Scatter(
            x=frame["datetime"],
            y=frame["ma"],
            mode="lines",
            name=f"MA-{row}",
            line=dict(width=1.6),
            showlegend=False,
        ),
        row=row,
        col=col,
    )

    fig.update_yaxes(title_text=title, row=row, col=col)


def _mark_similarity_region(
    fig: go.Figure,
    row: int,
    col: int,
    start_dt: pd.Timestamp,
    end_dt: pd.Timestamp,
    label: str,
) -> None:
    """Highlight similar pattern region and mark start/end points."""

    fig.add_vrect(
        x0=start_dt,
        x1=end_dt,
        fillcolor="LightSkyBlue",
        opacity=0.18,
        line_width=0,
        row=row,
        col=col,
    )

    fig.add_vline(
        x=start_dt,
        line_dash="dot",
        line_color="royalblue",
        row=row,
        col=col,
    )
    fig.add_vline(
        x=end_dt,
        line_dash="dash",
        line_color="firebrick",
        row=row,
        col=col,
    )

    fig.add_annotation(
        x=start_dt,
        y=1.02,
        yref=f"y{'' if row == 1 else row} domain",
        xref=f"x{'' if row == 1 else row}",
        text=f"{label} start",
        showarrow=False,
        font=dict(size=10, color="royalblue"),
    )
    fig.add_annotation(
        x=end_dt,
        y=1.02,
        yref=f"y{'' if row == 1 else row} domain",
        xref=f"x{'' if row == 1 else row}",
        text=f"{label} end",
        showarrow=False,
        font=dict(size=10, color="firebrick"),
    )


def _center_axis_on_timestamp(
    fig: go.Figure,
    row: int,
    col: int,
    center_dt: pd.Timestamp,
    left_bars: int,
    right_bars: int,
    bar_delta: timedelta,
) -> None:
    """Set x-axis range so that center_dt appears near the middle."""

    start = center_dt - (bar_delta * left_bars)
    end = center_dt + (bar_delta * right_bars)
    fig.update_xaxes(range=[start, end], row=row, col=col)


def save_combined_chart(
    df: pd.DataFrame,
    settings: Settings,
    candidates: List[CandidateMatch],
    output_dir: str = "charts",
) -> Path:
    """Save one HTML with vertical charts: current + top candidates."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fig = make_subplots(
        rows=1 + len(candidates),
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.04,
        subplot_titles=["Current"] + [f"Candidate {c.rank}" for c in candidates],
    )

    bar_delta = _get_bar_delta(df)

    # Current panel
    if settings.logic_type == "candle_shape_v2":
        active_pattern_length = settings.candle_pattern_length
    elif settings.logic_type == "ma_gap_structure_v1":
        active_pattern_length = settings.ma_gap_pattern_length
    else:
        active_pattern_length = settings.pattern_length

    current_left_ctx = active_pattern_length + 10
    current_right_ctx = active_pattern_length + 10
    cur_start = max(0, len(df) - active_pattern_length - 10)
    current_frame = df.iloc[cur_start:].copy()

    target_start_idx = len(df) - active_pattern_length
    target_start_dt = df["datetime"].iloc[target_start_idx]
    target_end_dt = df["datetime"].iloc[-1]

    current_gap = float(df["gap"].iloc[target_start_idx])
    current_title = (
        f"Current | start={target_start_dt} | score=N/A | gap={current_gap:.4f}"
    )
    _add_candles_and_ma(fig, 1, 1, current_frame, current_title)
    _mark_similarity_region(fig, 1, 1, target_start_dt, target_end_dt, "target")

    # 最新値（target end）がチャート中央に見えるようにレンジを固定
    _center_axis_on_timestamp(
        fig,
        1,
        1,
        center_dt=target_end_dt,
        left_bars=current_left_ctx,
        right_bars=current_right_ctx,
        bar_delta=bar_delta,
    )

    # Candidate panels
    for panel_row, c in enumerate(candidates, start=2):
        cand_context_left = 10

        plot_start = max(0, c.start_idx - cand_context_left)
        plot_end = min(
            len(df) - 1,
            c.end_idx + settings.candidate_chart_future_bars + 10,
        )
        frame = df.iloc[plot_start : plot_end + 1].copy()

        title = (
            f"Candidate {c.rank} | start={c.candidate_start_datetime} | score={c.score:.4f} "
            f"| gap={c.candidate_gap:.4f} | future_return={c.future_return:.4f}"
        )
        if c.logic_type == "candle_shape_v2":
            s = c.summary_stats
            title += (
                f" | bull/bear={int(s.get('bullish_count', 0))}/{int(s.get('bearish_count', 0))}"
                f" | avg_body={s.get('average_body_ratio', 0):.3f}"
                f" | avg_up={s.get('average_upper_wick_ratio', 0):.3f}"
                f" | avg_low={s.get('average_lower_wick_ratio', 0):.3f}"
            )
        elif c.logic_type == "ma_gap_structure_v1":
            s = c.summary_stats
            title += (
                f" | avg_ema_sma={s.get('average_ema_sma_gap_pct', 0):.4f}"
                f" | avg_close_ema={s.get('average_close_ema_gap_pct', 0):.4f}"
                f" | sign_match={s.get('sign_match_ratio', 0):.3f}"
            )
        elif c.logic_type == "env_mask_zscore_v4":
            s = c.summary_stats
            title += (
                f" | pred_ret20={s.get('predicted_return_after_20', 0):.4f}"
                f" | pred_px20={s.get('predicted_price_after_20', 0):.3f}"
            )
        _add_candles_and_ma(fig, panel_row, 1, frame, title)

        cand_start_dt = df["datetime"].iloc[c.start_idx]
        cand_end_dt = df["datetime"].iloc[c.end_idx]
        _mark_similarity_region(fig, panel_row, 1, cand_start_dt, cand_end_dt, f"cand{c.rank}")

        # 類似区間の終点（候補側）を現在チャートの最新点と同じ“中央位置”に合わせる
        _center_axis_on_timestamp(
            fig,
            panel_row,
            1,
            center_dt=cand_end_dt,
            left_bars=current_left_ctx,
            right_bars=current_right_ctx,
            bar_delta=bar_delta,
        )

    fig.update_layout(
        height=1300,
        width=1200,
        title_text=f"FX Pattern Similarity ({settings.symbol}, {settings.timeframe})",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
    )

    file_path = output_path / "pattern_report.html"
    fig.write_html(str(file_path), include_plotlyjs="cdn")
    return file_path



def save_env_mask_v4_report(df: pd.DataFrame, settings: Settings, candidates: List[CandidateMatch], output_dir: str = "charts") -> Path:
    """Create two-chart HTML for logic4: full period + compare/forecast."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    close = df["close"].to_numpy(dtype=float)
    ma = df["close"].rolling(settings.ma_window).mean()
    x = df["datetime"]

    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.12, subplot_titles=["全期間チャート", "比較・予測チャート"]) 

    # 1) full period
    fig.add_trace(go.Scatter(x=x, y=close, name="close", mode="lines"), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=ma, name=f"MA{settings.ma_window}", mode="lines"), row=1, col=1)
    for c in candidates:
        fig.add_trace(
            go.Scatter(
                x=[df["datetime"].iloc[c.end_idx]],
                y=[df["close"].iloc[c.end_idx]],
                mode="markers",
                marker=dict(size=10),
                name=f"cand{c.rank}",
            ),
            row=1,
            col=1,
        )

    # 2) comparison + forecast (% from each pattern start, forecast scaled to current)
    w = settings.env_window_size
    h = settings.env_forecast_horizon
    target_start = len(df) - w
    target_close = close[target_start:]
    target_pct = (target_close / target_close[0]) - 1
    tx = list(range(-w + 1, 1))
    fig.add_trace(go.Scatter(x=tx, y=target_pct, name="current_pattern", mode="lines", line=dict(width=3)), row=2, col=1)

    current_price = close[-1]
    for c in candidates:
        hist = close[c.start_idx : c.end_idx + 1]
        hist_pct = (hist / hist[0]) - 1
        hx = list(range(-w + 1, 1))
        fig.add_trace(go.Scatter(x=hx, y=hist_pct, name=f"cand{c.rank}_hist", mode="lines"), row=2, col=1)

        fut = close[c.end_idx : c.end_idx + h + 1]
        fut_pct = (fut / fut[0]) - 1
        fut_price_curve = current_price * (1 + fut_pct)
        fut_curve_pct_from_current = (fut_price_curve / current_price) - 1
        fx = list(range(0, h + 1))
        fig.add_trace(go.Scatter(x=fx, y=fut_curve_pct_from_current, name=f"cand{c.rank}_forecast", mode="lines", line=dict(dash="dot")), row=2, col=1)

    fig.update_layout(height=1000, width=1200, template="plotly_white", title="Logic4: Environment-aware Similarity + Forecast")

    out_file = output_path / "pattern_report_logic4.html"
    fig.write_html(str(out_file), include_plotlyjs="cdn")
    return out_file
