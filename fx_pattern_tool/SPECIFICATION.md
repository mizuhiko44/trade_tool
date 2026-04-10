# FX Pattern Tool 現状設計仕様書

本仕様書は、現行実装（`fx_pattern_tool/`）の挙動をコードベースで整理したものです。

---

## 1. 目的

- FX の OHLC データを取得し、直近の Close パターンに類似する過去パターンを探索する。
- 200本移動平均（`ma_window`）に対する GAP も加味してスコアリングする。
- 現状チャートと候補チャート（上位 `top_k`）を Plotly のローソク足で表示する。

---

## 2. システム構成

| ファイル | 役割 |
|---|---|
| `app.py` | エントリポイント。設定読込、データ取得、特徴量計算、類似探索、結果表示、HTML出力を実行 |
| `config.py` | `Settings` dataclassで実行パラメータ管理 |
| `data_source.py` | Alpha Vantage取得とCSVフォールバック、OHLC整形 |
| `pattern_finder.py` | 正規化、MA/GAP計算、類似度計算、候補抽出 |
| `chart_view.py` | 現状＋候補をサブプロットで可視化してHTML保存 |
| `utils.py` | ログ、ディレクトリ作成、通貨ペア分解補助 |

---

## 3. 設定仕様（`Settings`）

主な設定項目:

- `symbol`（例: `USDJPY`）
- `timeframe`（`daily`, `weekly`, `60min`, `15min` など）
- `pattern_length`（類似比較対象の本数）
- `future_length`（候補の将来騰落率計算に使う本数）
- `top_k`（表示候補数）
- `ma_window`（移動平均期間）
- `exclude_recent_bars`（直近との重なり除外）
- `gap_weight`（GAP距離の重み）
- `candidate_chart_future_bars`（候補チャートで候補終了後に表示する本数。初期値5）

---

## 4. データ取得仕様

### 4.1 Alpha Vantage

- APIキーは `.env` の `ALPHAVANTAGE_API_KEY` を使用。
- `symbol` は6文字通貨ペア（例: `USDJPY`）を `from_symbol=USD`, `to_symbol=JPY` に分解。
- `timeframe == "daily"` の場合:
  - `function=FX_DAILY`
- `timeframe == "weekly"` の場合:
  - `function=FX_WEEKLY`
- それ以外の場合:
  - `function=FX_INTRADAY`
  - `interval=timeframe`

### 4.2 CSVフォールバック

以下の場合、CSVフォールバックを実行:

- APIキー未設定
- APIレスポンス異常
- 通信エラー
- `data_source != "alpha_vantage"`

フォールバック先:

- `sample_data/sample_usdjpy_daily.csv`（設定で変更可能）

### 4.3 共通整形

取得後は以下に正規化:

- 必須列: `datetime, open, high, low, close`
- `datetime` を `datetime64` 化
- OHLCを数値化
- 欠損削除
- `datetime` 昇順ソート

---

## 5. 類似判定ロジック（詳細）

本ツールの類似判定は、**Close形状の距離** と **GAP距離** の合成スコアです。

### 5.1 特徴量

1. 移動平均

- `ma = close.rolling(ma_window).mean()`

2. GAP

- `gap = (close - ma) / ma`

### 5.2 ターゲット（現状）定義

- 直近 `pattern_length` 本をターゲット区間とする。
- インデックスで表すと:
  - `target_start = len(df) - pattern_length`
  - `target_end = len(df) - 1`

### 5.3 正規化

Close系列は始点基準の比率で正規化:

- `normalize(series) = (series / series[0]) - 1`
- 始点がほぼ0の場合のみ差分正規化:
  - `series - series[0]`

### 5.4 候補区間の生成

候補開始インデックス `start_idx` を以下範囲で走査:

- `0 ... max_candidate_start`
- `max_candidate_start = len(df) - exclude_recent_bars - pattern_length - future_length`

候補区間:

- `end_idx = start_idx + pattern_length - 1`

この範囲設計により:

- ターゲット近傍との重なりを `exclude_recent_bars` で除外
- `future_return` 計算に必要な将来バー（`future_length`）を確保

### 5.5 距離計算

#### A. Close形状距離（shape_distance）

- ターゲット正規化系列と候補正規化系列の二乗誤差和:

`shape_distance = Σ (target_norm[i] - candidate_norm[i])^2`

#### B. GAP距離（gap_distance）

- ターゲット開始時点のGAPと候補開始時点のGAPの絶対差:

`gap_distance = abs(target_gap - candidate_gap)`

### 5.6 総合スコア

- `score = shape_distance + gap_weight * gap_distance`
- 小さいほど類似。

### 5.7 future_return

候補ごとに将来騰落率を算出:

- `future_idx = end_idx + future_length`
- `future_return = (close[future_idx] / close[end_idx]) - 1`

### 5.8 最終候補

- `score` 昇順でソートし、上位 `top_k` を採用。
- `rank` を1始まりで付与。

---

## 6. チャート仕様

`chart_view.save_combined_chart` は 1つのHTMLに縦並びサブプロットを作成する。

- 行1: 現状（Current）
- 行2: 候補1（Candidate 1）
- 行3: 候補2（Candidate 2）
- 行4: 候補3（Candidate 3）
  - `top_k` が3以外なら行数も可変

各行の内容:

- ローソク足（OHLC）
- MA折れ線（`ma`）
- 行タイトルに開始日時/score/gap/future_return等を表示

---

## 7. 現在チャートと候補チャートの位置対応仕様

### 7.1 現状（Current）行の範囲

- `cur_start = max(0, len(df) - pattern_length - 10)`
- 表示区間は `df[cur_start:]`

意味:

- 直近 `pattern_length` 本に加えて左側に10本の文脈を表示

### 7.2 候補（Candidate）行の範囲

候補 `c` について:

- `plot_start = c.start_idx`
- `plot_end = c.end_idx + candidate_chart_future_bars`（上限は末尾でクリップ）

意味:

- 候補パターン本体 `pattern_length` 本
- その後ろに `candidate_chart_future_bars` 本（初期値5本）

### 7.3 現状と候補の「位置」の対応づけ

このツールは「時間軸の絶対日時」を一致させるのではなく、**パターンの相対位置**で比較する。

- 現状行: 右端付近に最新パターン
- 候補行: 各候補の開始点から同じ長さのパターン区間を表示

したがって、比較対象は以下:

- パターン先頭（開始点）を基準にしたCloseの形
- 開始時点GAP
- 候補終了後の将来推移（チャート上は最大5本）

---

## 8. CLI出力仕様

標準出力に以下を表示:

- `symbol`, `timeframe`, `data_count`
- `current_close`, `current_ma`, `current_gap`
- `target_start_datetime`
- 候補一覧（rank, candidate_start_datetime, score, gap, future_return）
- 保存チャートファイルパス

---

## 9. 既知制約

- 類似距離は単純な二乗誤差和のため、時間伸縮や局所位相ずれには未対応。
- `future_return` 算出は `future_length` を使う一方、候補チャート表示は `candidate_chart_future_bars` を使うため、
  「表示本数」と「評価本数」は必ずしも一致しない。
- Alpha Vantageの無料枠制限時はCSVフォールバックになる。


## 10. 複数ロジック対応（現行）

- `logic_type = "close_pattern_v1"`
  - Close系列の正規化形状 + 開始時gap差
- `logic_type = "candle_shape_v2"`
  - 10本（`candle_pattern_length`）の足について、
    - 各足の形状差分
    - direction/categoryの並び一致
    - 2本組パターン一致
    - 集計特徴一致
  を合算した `final_score` で評価

`candle_shape_v2` の候補には、以下メタ情報も保持する。

- average_body_ratio
- average_upper_wick_ratio
- average_lower_wick_ratio
- bullish_count / bearish_count / neutral_count
- direction_mismatch_count
- category_mismatch_count
- pair_mismatch_count
