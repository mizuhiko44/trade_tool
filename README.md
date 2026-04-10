# trade_tool

`fx_pattern_tool/` は **FX Pattern Analyzer Desktop**（PySide6）として動作します。

## セットアップ

```bash
cd fx_pattern_tool
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` に以下を設定してください。

```env
ALPHAVANTAGE_API_KEY=your_alpha_vantage_api_key_here
```

## GUI起動方法

```bash
cd fx_pattern_tool
python app.py
```

## 機能

- GUIで通貨ペア/時間足/ロジック/データ取得方法を選択
- 分析ロジック切替
  - `close_pattern_v1`
  - `candle_shape_v2`
  - `ma_gap_structure_v1`
- local / latest 切替、latest失敗時のlocalフォールバック有無
- 候補一覧テーブル表示
- Plotlyチャート（現状＋候補）をGUI内表示

## 設計仕様書

- `fx_pattern_tool/SPECIFICATION.md`


## PySide6が無い場合

`python app.py` 実行時に PySide6 が無い場合は、Tkinter フォールバックGUIが自動起動します。
