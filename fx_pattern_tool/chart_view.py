"""Plotly chart generation for current and candidate patterns."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import Settings
from pattern_finder import CandidateMatch


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


def save_combined_chart(
    df: pd.DataFrame,
    settings: Settings,
    candidates: List[CandidateMatch],
    output_dir: str = "charts",
) -> Path:
    """Save one HTML with 4 vertical charts: current + top3 candidates."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fig = make_subplots(
        rows=1 + len(candidates),
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.04,
        subplot_titles=["Current"] + [f"Candidate {c.rank}" for c in candidates],
    )

    # Current panel: include a little left margin for context
    cur_start = max(0, len(df) - settings.pattern_length - 10)
    current_frame = df.iloc[cur_start:].copy()
    current_gap = float(df["gap"].iloc[len(df) - settings.pattern_length])
    current_title = (
        f"Current | start={df['datetime'].iloc[len(df)-settings.pattern_length]} "
        f"| score=N/A | gap={current_gap:.4f}"
    )
    _add_candles_and_ma(fig, 1, 1, current_frame, current_title)

    # Candidate panels
    for panel_row, c in enumerate(candidates, start=2):
        plot_start = c.start_idx
        plot_end = min(len(df) - 1, c.end_idx + settings.future_length)
        frame = df.iloc[plot_start : plot_end + 1].copy()

        title = (
            f"Candidate {c.rank} | start={c.candidate_start_datetime} | score={c.score:.4f} "
            f"| gap={c.candidate_gap:.4f} | future_return={c.future_return:.4f}"
        )
        _add_candles_and_ma(fig, panel_row, 1, frame, title)

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
