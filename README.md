# trade_tool

このリポジトリには `fx_pattern_tool/` 配下にFXパターン探索CLIツールが入っています。

## クイックスタート

### 1) ツールディレクトリに移動
```bash
cd fx_pattern_tool
```

### 2) 依存関係をインストール
```bash
pip install -r requirements.txt
```

> ルートディレクトリ (`/workspace/trade_tool`) でそのまま `pip install -r requirements.txt` を実行した場合でも動くよう、
> ルートにも同じ依存を記載した `requirements.txt` を配置しています。

### 3) `.env` を作成
```bash
cp .env.example .env
# ルートで実行する場合も同じコマンドでOK（ルートにも .env.example あり）
```

`.env` に Alpha Vantage API キーを設定してください。

```env
ALPHAVANTAGE_API_KEY=your_alpha_vantage_api_key_here
```

### 4) 実行
```bash
python app.py
```

## よくあるエラー

- `Could not open requirements file` が出る場合
  - 実行ディレクトリと `requirements.txt` の位置が合っていない可能性があります。
  - `cd fx_pattern_tool` 後に `pip install -r requirements.txt` を実行してください。

## 設計仕様書

- 現状設計仕様は `fx_pattern_tool/SPECIFICATION.md` を参照してください。


## timeframeの例

- `daily`
- `weekly`
- `60min`
- `15min`
