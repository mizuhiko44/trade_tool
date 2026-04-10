"""Tkinter fallback GUI for environments without PySide6."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from chart_view import save_combined_chart
from config import (
    AVAILABLE_DATA_MODES,
    AVAILABLE_LOGIC_TYPES,
    AVAILABLE_SYMBOLS,
    AVAILABLE_TIMEFRAMES,
    LOGIC_LABELS,
    Settings,
    validate_data_mode,
    validate_logic_type,
)
from data_source import (
    fetch_alpha_vantage_ohlc,
    load_csv_fallback,
    load_local_symbol_timeframe_csv,
    save_ohlc_to_local_csv,
)
from pattern_finder import add_features, find_similar_patterns


class FXPatternAnalyzerTkApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FX Pattern Analyzer Desktop (Tkinter fallback)")
        self.root.geometry("1200x850")

        self.status_var = tk.StringVar(value="待機中")
        self.api_time_var = tk.StringVar(value="データ取得日時: -")
        self.source_var = tk.StringVar(value="実際の使用データ: -")
        self.summary_var = tk.StringVar(value="未実行")
        self.chart_path_var = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.LabelFrame(self.root, text="設定")
        top.pack(fill="x", padx=8, pady=6)

        self.symbol_var = tk.StringVar(value=AVAILABLE_SYMBOLS[0])
        self.timeframe_var = tk.StringVar(value=AVAILABLE_TIMEFRAMES[0])
        self.logic_var = tk.StringVar(value=AVAILABLE_LOGIC_TYPES[0])
        self.data_mode_var = tk.StringVar(value=AVAILABLE_DATA_MODES[0])
        self.topk_var = tk.IntVar(value=3)
        self.pattern_len_var = tk.IntVar(value=30)
        self.fallback_var = tk.BooleanVar(value=True)

        row1 = ttk.Frame(top)
        row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="通貨ペア").pack(side="left")
        ttk.Combobox(row1, textvariable=self.symbol_var, values=AVAILABLE_SYMBOLS, width=12, state="readonly").pack(side="left", padx=4)
        ttk.Label(row1, text="時間足").pack(side="left", padx=(12, 0))
        ttk.Combobox(row1, textvariable=self.timeframe_var, values=AVAILABLE_TIMEFRAMES, width=10, state="readonly").pack(side="left", padx=4)

        row2 = ttk.Frame(top)
        row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="分析ロジック").pack(side="left")
        logic_display = [f"{LOGIC_LABELS[x]} ({x})" for x in AVAILABLE_LOGIC_TYPES]
        self.logic_combo = ttk.Combobox(row2, values=logic_display, width=40, state="readonly")
        self.logic_combo.current(0)
        self.logic_combo.pack(side="left", padx=4)
        self.logic_combo.bind("<<ComboboxSelected>>", self._on_logic_changed)

        ttk.Label(row2, text="データ取得").pack(side="left", padx=(12, 0))
        ttk.Combobox(row2, textvariable=self.data_mode_var, values=AVAILABLE_DATA_MODES, width=8, state="readonly").pack(side="left", padx=4)

        row3 = ttk.Frame(top)
        row3.pack(fill="x", padx=6, pady=4)
        ttk.Label(row3, text="候補件数").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=10, textvariable=self.topk_var, width=6).pack(side="left", padx=4)
        ttk.Label(row3, text="比較本数").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row3, from_=5, to=200, textvariable=self.pattern_len_var, width=6).pack(side="left", padx=4)
        ttk.Checkbutton(row3, text="latest失敗時にlocalへフォールバック", variable=self.fallback_var).pack(side="left", padx=12)

        self.run_btn = ttk.Button(top, text="分析実行", command=self.run_analysis)
        self.run_btn.pack(anchor="w", padx=6, pady=6)

        status = ttk.LabelFrame(self.root, text="ステータス")
        status.pack(fill="x", padx=8, pady=6)
        ttk.Label(status, textvariable=self.status_var).pack(anchor="w", padx=6)
        ttk.Label(status, textvariable=self.api_time_var).pack(anchor="w", padx=6)
        ttk.Label(status, textvariable=self.source_var).pack(anchor="w", padx=6)

        summary = ttk.LabelFrame(self.root, text="条件サマリー")
        summary.pack(fill="x", padx=8, pady=6)
        ttk.Label(summary, textvariable=self.summary_var).pack(anchor="w", padx=6)

        table_frame = ttk.LabelFrame(self.root, text="候補一覧")
        table_frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(table_frame, columns=("rank", "start", "score", "future"), show="headings", height=9)
        for col, w in [("rank", 60), ("start", 180), ("score", 120), ("future", 120)]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w)
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        chart = ttk.LabelFrame(self.root, text="チャート")
        chart.pack(fill="x", padx=8, pady=6)
        ttk.Label(chart, text="チャートHTML: ").pack(side="left", padx=6)
        ttk.Label(chart, textvariable=self.chart_path_var).pack(side="left", padx=6)
        ttk.Button(chart, text="ブラウザで開く", command=self._open_chart).pack(side="right", padx=6)

    def _on_logic_changed(self, _event=None) -> None:
        selected = self.logic_combo.get()
        logic = selected.split("(")[-1].strip(")")
        self.logic_var.set(logic)
        self.pattern_len_var.set(30 if logic == "close_pattern_v1" else 10)

    def _build_settings(self) -> Settings:
        settings = Settings()
        settings.symbol = self.symbol_var.get()
        settings.timeframe = self.timeframe_var.get()
        settings.logic_type = self.logic_var.get()
        settings.data_mode = self.data_mode_var.get()
        settings.top_k = int(self.topk_var.get())
        settings.fallback_to_local = bool(self.fallback_var.get())

        n = int(self.pattern_len_var.get())
        if settings.logic_type == "close_pattern_v1":
            settings.pattern_length = n
        elif settings.logic_type == "candle_shape_v2":
            settings.candle_pattern_length = n
        else:
            settings.ma_gap_pattern_length = n
        return settings

    def run_analysis(self) -> None:
        self.run_btn.configure(state="disabled")
        self.status_var.set("分析中...")
        th = threading.Thread(target=self._run_analysis_job, daemon=True)
        th.start()

    def _run_analysis_job(self) -> None:
        try:
            settings = self._build_settings()
            validate_logic_type(settings.logic_type)
            validate_data_mode(settings.data_mode)

            self._set_status("データ取得中...")
            df, source_label, fetched_at = self._load_data(settings)

            self._set_status("類似パターン探索中...")
            df = add_features(df, settings.ma_window)
            df = df.dropna(subset=["ma", "gap"]).reset_index(drop=True)
            matches = find_similar_patterns(df, settings)

            self._set_status("チャート生成中...")
            report = save_combined_chart(df, settings, matches, output_dir=settings.charts_dir)

            self.root.after(0, lambda: self._show_result(settings, matches, report, source_label, fetched_at))
        except Exception as exc:
            self.root.after(0, lambda: self._on_error(str(exc)))

    def _load_data(self, settings: Settings):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if settings.data_mode == "local":
            try:
                return load_local_symbol_timeframe_csv(settings), "local CSV", "N/A"
            except Exception:
                return load_csv_fallback(settings), "local fallback(sample)", "N/A"

        try:
            df = fetch_alpha_vantage_ohlc(settings)
            save_ohlc_to_local_csv(df, settings)
            return df, "latest API", now
        except Exception as api_exc:
            if settings.fallback_to_local:
                try:
                    return load_local_symbol_timeframe_csv(settings), f"latest失敗→local ({api_exc})", "N/A"
                except Exception:
                    return load_csv_fallback(settings), f"latest失敗→sample ({api_exc})", "N/A"
            raise RuntimeError(f"API取得失敗: {api_exc}")

    def _show_result(self, settings: Settings, matches, report: Path, source_label: str, fetched_at: str) -> None:
        self.status_var.set("完了")
        self.api_time_var.set(f"データ取得日時: {fetched_at}")
        self.source_var.set(f"実際の使用データ: {source_label}")
        self.summary_var.set(
            f"symbol={settings.symbol}, timeframe={settings.timeframe}, logic={settings.logic_type}, "
            f"data_mode={settings.data_mode}, top_k={settings.top_k}, fallback={settings.fallback_to_local}"
        )
        self.chart_path_var.set(str(report.resolve()))

        for i in self.tree.get_children():
            self.tree.delete(i)
        for m in matches:
            self.tree.insert("", "end", values=(m.rank, str(m.candidate_start_datetime), f"{m.score:.6f}", f"{m.future_return:.6f}"))

        self.run_btn.configure(state="normal")

    def _on_error(self, msg: str) -> None:
        self.status_var.set(f"エラー: {msg}")
        self.run_btn.configure(state="normal")
        messagebox.showerror("分析エラー", msg)

    def _set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    def _open_chart(self) -> None:
        p = self.chart_path_var.get().strip()
        if not p:
            return
        import webbrowser

        webbrowser.open(Path(p).resolve().as_uri())


def run_tk_app() -> None:
    root = tk.Tk()
    app = FXPatternAnalyzerTkApp(root)
    root.mainloop()
