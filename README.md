# AI Wikipedia Golf

WikipediaゴルフをLLMで自動プレイし、攻略本を改善し続けるためのツールです。ランダムに抽出したスタート/ゴール間をWikipediaのリンクだけで最短移動する「Wikipediaゴルフ」を複数回プレイし、その結果を攻略本にフィードバックします。

## 特長
- OpenRouter(OpenAI SDK) または Gemini API(google-generativeai) によるLLM実行をサポート
- Wikipedia APIを使ったスタート/ゴール選定とリンク探索を自動化
- 各プレイのプロンプト・応答ログ、移動履歴、トークンコストをYAMLで保存
- 20手・リンク100件制限や「数字を含むリンクを除外」などゲームルールを強制
- 指定イテレーションの攻略本を評価データセット(10組)で自動採点
- Gradioベースの可視化ダッシュボードで履歴・チャット・攻略本を閲覧

## セットアップ
1. Python 3.12 と [uv](https://github.com/astral-sh/uv) をインストールします。
2. 仮想環境を作成し依存関係を導入します。
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```
3. `.env` にAPIキーを設定します (例)。
   ```env
   GEMINI_API_KEY="your-key"
   OPENROUTER_API_KEY="optional-key"
   ```
   `python-dotenv` が `experiments/<name>/.env` とプロジェクト直下の `.env` を自動ロードします。

## 設定ファイル
各 experiment ディレクトリには少なくとも以下を配置します。

```
experiments/gemini/
├── config.yaml
└── .env            # 必要に応じて(任意)
```

`config.yaml` 例(Gemini 2.5 Flash Lite)。

```yaml
llm:
  provider: gemini
  model: gemini-2.5-flash-lite
  options:
    temperature: 0.7
    max_output_tokens: 1024
game:
  max_steps: 20
  max_links: 100
  exclude_digit_links: true
  retry_limit: 3
loop:
  iterations: 3
```

`evaluation_pairs` を `config.yaml` へ直接記載するか、`experiments/<name>/evaluation_pairs.yaml` もしくは `data/eval_pairs.yaml` (同梱) を利用します。

## コマンド
すべて `ai-wiki-golf` CLI から実行します。

- `ai-wiki-golf run experiments/gemini`
  - 初期攻略本生成 → ループ実行 → `books/{i}.txt`, `logs/{i}.yaml` を出力
- `ai-wiki-golf evaluate experiments/gemini`
  - `books/{i}.txt (i=1,21,41,61,81)` を対象に10組データで評価し、`evaluates/*.yaml` を保存
- `ai-wiki-golf viz experiments/gemini`
  - Gradioダッシュボードを起動し、過去ログや攻略本を閲覧

## ログ形式
`logs/{i}.yaml` は以下情報を含みます。

```yaml
config: <config全体のコピー>
messages:
  - role: user
    content: "..."
  - role: assistant
    content: "..."
game:
  start: "東京"
  goal: "富士山"
  score: 3
  history:
    - current: "東京"
      candidates: ["東京都", "日本", ...]
      choice: "関東地方"
cost:
  input_tokens: 1234
  output_tokens: 987
```

## 開発メモ
- Wikipedia APIアクセスは `src/ai_wiki_golf/mediawiki.py` (sample/mediawiki.pyを移植) を使用
- LLMプロンプトではゲームルール・攻略本・現在状態を毎ターン提示し、最後の行で `移動先: XXX` を必須化
- 失敗時スコアは 9999、候補はリンク100件＋過去訪問の順で提示します
- 攻略本は常に日本語1000文字以内にトリミングされ、オーバー時は再生成を依頼します
