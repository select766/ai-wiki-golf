# AI Wikipedia Golf – Agent Notes

## プロジェクトの目的と概要
- 目的: LLM をプレイヤーに据え、Wikipediaゴルフを自動プレイさせながら「攻略本」を継続的に改善する。
- 成果物: 各実験ディレクトリに攻略本のバージョン履歴(`books/*.txt`)と詳細ログ(`logs/*.yaml`)を蓄積し、評価用ペアでスコアを比較する。

## Wikipediaゴルフとは
- Wikipediaからランダムに選ばれたスタート/ゴールの2ページ間を、Wikipediaのリンクのみで20手以内に到達する1人プレイゲーム。
- 行動コストはクリック数。少ないほど高得点。
- 本システムでは日本語版Wikipediaを対象とし、ページ本文は参照せず「ページ名」と「リンク先一覧(最大100件)」のみをLLMに渡す。

## ゲームルール（LLM向け）
1. スタートとゴールはWikipedia APIのランダムエンドポイントで決定する。
2. 1ターンで可能なのは「現在ページに存在するリンクへ移動」または「過去に訪れたページへ戻る」のみ。
3. 20ターン以内にゴールへ到達できなければ失敗スコア(9999)となる。
4. 数字(0-9,全角含む)を含むリンクは候補から除外して提示し、プロンプトでも禁止ルールを説明する。
5. LLMは思考過程を文章で述べ、最後の行を `移動先: 候補名` の形式で出力する。
6. 初回ターンのみ攻略本とルール要約・ゴール概要を提示し、2ターン目以降は状況のみを渡す。

## 1プレイの詳細フロー
1. スタート/ゴールを決定し、履歴にスタートをセット。
2. 現在ページからリンク一覧(設定 `max_links`)を取得し、過去に訪れたページも候補先頭に並べる。
3. LLMへ以下をプロンプト: ルール説明(初回のみ) + 攻略本 + 現在地/履歴/候補/ターン/ゴール概要。
4. LLMのレスポンスから `移動先` を抽出し検証。無効なら最大 `retry_limit` まで再プロンプト。
5. 選択ページへ移動し履歴とステップログを更新。ゴールなら成功終了。
6. 上限ターンに達したら失敗。最後にチャット履歴+移動履歴を使って攻略本の改善をLLMに依頼し、1000文字以内に整形して保存。

## 攻略本アップデート方針
- 1000文字以内、日本語、単体で読んでも成立する実践的テクニック集。
- 成功/失敗といった語や固有名詞、禁止語(今回/プレイ等)を除去して汎化。
- 必ず数字リンク除外ルールへの言及を入れる。

## ループ(Experiment)の実装
- 各 experiment ディレクトリ構成:
```
experiments/<name>/
├── config.yaml          # LLM・ゲーム・ループ設定
├── .env                 # APIキー (任意)
├── books/
│   ├── 0.txt            # 初期攻略本
│   └── N.txt            # 各プレイ後の攻略本
├── logs/
│   └── N.yaml           # チャット＆ゲーム履歴
└── evaluates/           # 評価実行時に作成
```
- ループ処理: `books/0.txt` を初期生成し、1..N で (旧攻略本→1プレイ→新攻略本保存→ログ保存) を繰り返す。
- ログフォーマット:
```
config: <configのコピー>
messages:
  - role: user
    content: "..."
  - role: assistant
    content: "..."
game:
  start: "東京"
  goal: "富士山"
  score: 3   # 失敗時9999
  history:
    - current: "東京"
      candidates: ["日本", ...]
      choice: "関東地方"
cost:
  input_tokens: ...
  output_tokens: ...
```

## 設定項目 (config.yaml)
- `llm`: provider(openrouter|gemini)、model、options(temperature, max_output_tokens 等)。OpenRouter利用時は base_url 指定可。
- `game`: `max_steps`、`max_links`、`exclude_digit_links`、`include_goal_abstract`、`retry_limit` などルール設定。
- `loop`: `iterations`、`seed`。
- `evaluation_pairs`: 省略時は `experiments/<name>/evaluation_pairs.yaml` または `data/eval_pairs.yaml` を使用。

## 評価
- 10組のスタート/ゴール固定ペアで攻略本の性能を比較。`books/{i}.txt (i=1,21,41,...)` を用い、結果は `evaluates/*.yaml` へ出力。
- スコアはクリック数の合計(小さいほど良い)。評価実行時は攻略本の再生成を行わない。

## 主要コマンド
- `source .venv/bin/activate` : uvで作成した仮想環境を有効化。
- `ai-wiki-golf run <experiment_dir>` : 初期攻略本生成 + プレイループを実行。
- `ai-wiki-golf evaluate <experiment_dir>` : 評価用データセットで自動プレイし `evaluates/` を生成。
- `ai-wiki-golf viz <experiment_dir>` : Gradioダッシュボードを起動し、過去プレイを閲覧。
- `python -m ensurepip && pip install -e .` : uv 環境に依存関係を導入（初回セットアップ時）。

## 実装方針の詳細
- **LLMドライバ** (`src/ai_wiki_golf/llm.py`): OpenRouter(OpenAI SDK互換)とGeminiを統一インターフェースで呼び出し。OpenRouterでは `max_output_tokens`→`max_tokens` 変換、Geminiでは quota 超過時の指数バックオフと複数回リトライを実装。
- **Wikipedia API** (`src/ai_wiki_golf/mediawiki.py`): ランダムページ、リンク一覧、概要を取得。固定User-Agentでアクセスし、欠損ページや100件超のリンクをハンドリング。
- **ゲームランナー** (`src/ai_wiki_golf/game.py`): 候補生成時に過去ページを優先列挙し、`exclude_digit_links` を正規表現で適用。1ターン目のみルール+攻略本を提示し、`移動先:` の抽出は最後に出現した行を採用。終了後は攻略本更新と長すぎる出力の再生成を行う。
- **実験制御** (`src/ai_wiki_golf/experiment.py`): `.env` とプロジェクト直下 `.env` を `python-dotenv` で読み込み、ループ結果を `books/` `logs/` に保存。
- **評価** (`src/ai_wiki_golf/evaluation.py`): 指定攻略本バージョンを評価ペアで実行し、結果を YAML へ。
- **可視化** (`src/ai_wiki_golf/visualize.py`): Gradio でログ一覧→詳細→チャット/攻略本閲覧を提供。

## 技術スタック・環境
- Python 3.12 / uv で仮想環境を構築。
- 依存: `typer`, `pyyaml`, `requests`, `python-dotenv`, `openai`, `google-generativeai`, `gradio`, `rich` など。
- LLMアクセス: OpenRouter経由(OpenAI SDK, base_url指定) と google-generativeai(Gemini)。
- `.env` で `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` を設定。experiment配下の `.env` も読み込まれる。
- Wikipedia APIヘッダや `sample/mediawiki.py` のロジックを `src/ai_wiki_golf/mediawiki.py` へコピーして利用。

## 初期デバッグ・運用手順
1. `uv venv` → `source .venv/bin/activate` → `python -m ensurepip && pip install -e .` で環境構築。
2. `.env` に Gemini/OpenRouter の API キーを設定。Gemini使用 config で `gemini-2.5-flash-lite` を指定。
3. `ai-wiki-golf run experiments/<name>` を実行し、初期攻略本生成 + 1プレイを確認。その後 `iterations: 3` 程度でループを実行。
4. 生成された `logs/*.yaml` を確認し、LLMの出力がフォーマット逸脱していればプロンプトを調整。
5. 必要に応じて `ai-wiki-golf evaluate` で評価、`ai-wiki-golf viz` で可視化確認。

## 注意点
- 数字リンク除外・20ターン制限などのルールは常にプロンプトとロジックで同期させる。
- 攻略本は常に1000文字以内・日本語で単体成立するよう整形し、禁止語をサニタイズする。
- `移動先:` の抽出は最後の出現を採用し、再試行も含めてログを残す。
- Wikipedia API は専用User-Agentを使い、アクセス過多で 403/429 を招かないよう注意。
- Geminiはレート制限が厳しいため、`GeminiClient` のリトライログを確認しながら長時間ループ時はディレイを考慮する。
