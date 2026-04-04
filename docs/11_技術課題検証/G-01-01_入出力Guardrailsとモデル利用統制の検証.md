# 入出力 Guardrails とモデル利用統制の検証

## 検証目的

本検証の主目的は、課題 G-01「入出力 Guardrails とモデル利用統制」について、PoC 環境で段階的に成立性を確認することである。ここで確認したいのは、単に NeMo Guardrails や LiteLLM Proxy が起動することではなく、自然言語の入出力統制とモデル利用統制を分離した構成が、実際に運用可能な形で組めるかどうかである。

本検証では、一度に最終形へ進まず、以下の 2 段階で確認する。

1. まず、ユーザーまたは AI エージェント -> LiteLLM Proxy -> LLM の構成により、モデル利用経路の固定、認証、モデル利用統制、軽量な入力ガードが成立するかを確認する。
2. その後、ユーザーまたは AI エージェント -> NeMo Guardrails -> LiteLLM Proxy -> LLM の構成に拡張し、入出力 Guardrails とモデル利用統制を責務分離した状態で成立させられるかを確認する。

最終的には、PoC の初期段階では LiteLLM Proxy によるモデル集約と軽量 Guardrails を先行させ、次段で NeMo Guardrails を前段に追加する二段構えが妥当かを判断できる状態を目指す。

## 関連するアーキテクチャ検討文書

本ドキュメントは、主に AI ガバナンス層の PoC 検証資料として位置付ける。あわせて、全体アーキテクチャ上の配置、周辺レイヤとの関係、技術課題への対応状況を補助的に確認するため、以下の文書と対応している。

- [04_AIエージェントの業務適用を見据えた生成AIガバナンス層の検討.md](../01_アーキテクチャ検討/04_AIエージェントの業務適用を見据えた生成AIガバナンス層の検討.md)
	- 入出力 Guardrails を独立レイヤーとして配置し、モデル利用統制と分離する考え方に直接対応する。NeMo Guardrails を前段に置く構成は、この文書で述べる AI ガバナンス層の具体的な PoC である。
- [01_AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md](../01_アーキテクチャ検討/01_AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md)
	- AI ガバナンス層、Application 層、Tool 層を含む全体構成の中で、LiteLLM Proxy と NeMo Guardrails がどこに位置付くかを確認するための上位文書である。
- [04_生成AIガバナンス層の実現方式.md](../02_アーキテクチャ実現方式/04_生成AIガバナンス層の実現方式.md)
	- PoC では LiteLLM Proxy の Hook による軽量実装を先行し、その後 NeMo Guardrails を前段に配置する二段構えを採る方針に対応する。
- [技術課題と対応方針.md](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
	- 課題 G-01「入出力 Guardrails とモデル利用統制」に対して、本検証がどの論点を実機で確認するかを整理する際の参照先である。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| G-01 | G-01-01 | LiteLLM Proxy をモデル利用経路の単一入口として固定し、認証と許可モデル統制を成立させられるかを確認する。 |
| G-01 | G-01-02 | LiteLLM Hook により、PoC 初期段階の軽量な入力ガードを実装できるかを確認する。 |
| G-01 | G-01-03 | NeMo Guardrails を前段に配置し、入出力 Guardrails と LiteLLM Proxy の責務分離を成立させられるかを確認する。 |

G-01-04 の Tool 利用上限と予算統制は本稿の主対象外であり、別の検証または後続フェーズで扱う前提とする。

## 検証で確認したいこと

今回の検証では、以下 2 フェーズを明確に分けて確認する。

### フェーズ 1: LiteLLM Proxy 単体によるモデル利用統制

- すべての LLM 呼び出しを LiteLLM Proxy 経由へ固定できる
- LiteLLM Proxy の認証キーにより、未許可クライアントからの利用を遮断できる
- `model_list` により利用可能モデルを固定できる
- LiteLLM Proxy の Hook により、PoC 初期段階の軽量な入力ガードを実装できる
- 正常系では upstream LLM まで到達し、遮断系では upstream へ送る前に止められる

### フェーズ 2: NeMo Guardrails 前段追加による入出力 Guardrails + モデル利用統制

- NeMo Guardrails が Guardrails API サーバーとして起動し、設定を読み込める
- NeMo Guardrails が入力 rail / 出力 rail を実施し、その後の LLM 呼び出しは LiteLLM Proxy 経由へ固定できる
- 正常入力では NeMo Guardrails を通過して LiteLLM Proxy -> LLM の応答が返る
- 危険入力では NeMo Guardrails が前段で拒否または安全な定型応答へ置換できる
- LiteLLM Proxy は引き続きモデル利用統制の主担当として機能し、NeMo Guardrails と責務分離できる

## 対象構成

今回の検証で使用する主な構成は、フェーズごとに次の通りとする。

### フェーズ 1 の構成

```mermaid
flowchart LR
	user["ユーザーまたは AI エージェント"]
	litellm["LiteLLM Proxy\nモデル利用統制\n軽量 Hook"]
	llm["許可された LLM"]

	user --> litellm
	litellm --> llm
```

図の見方:

- LiteLLM Proxy がモデル利用経路の単一入口となる
- 利用可能モデル、認証、軽量ガードを LiteLLM Proxy 側で扱う
- この段階では NeMo Guardrails はまだ導入しない

### フェーズ 2 の構成

```mermaid
flowchart LR
	user["ユーザーまたは AI エージェント"]
	nemo["NeMo Guardrails\n入力/出力 Guardrails"]
	litellm["LiteLLM Proxy\nモデル利用統制"]
	llm["許可された LLM"]

	user --> nemo
	nemo --> litellm
	litellm --> llm
```

図の見方:

- NeMo Guardrails が自然言語の入出力統制を担当する
- LiteLLM Proxy がモデル利用経路、認証、予算、モデル選択を担当する
- 両者を分離することで、意味論的 Guardrails とモデル利用統制を独立して扱えるようにする

### コンポーネント別の役割

| コンポーネント | 役割 | 主な配置 |
| --- | --- | --- |
| LiteLLM Proxy | モデル利用経路の固定、認証、利用可能モデルの制御、軽量 Hook | `infra/02-litellm` |
| LiteLLM Hook | PoC 初期段階の入力遮断、メタデータ付与 | `infra/02-litellm/src/ai_platform_litellm` |
| NeMo Guardrails | 入力 rails / 出力 rails による意味論的 Guardrails | `infra/03-nemo-guardrails` |
| PostgreSQL | LiteLLM Proxy の内部 DB | `infra/01-postgresql` |
| Langfuse | 将来のトレース集約・評価格納先 | `infra/11-langfuse` |

## 検証の考え方

### フェーズ 1 で確認する理由

NeMo Guardrails を前段に追加する前に、まず LiteLLM Proxy 単体でモデル利用統制の基礎が成立するかを切り分ける。ここで成立していない場合、後段の NeMo Guardrails 構成を追加しても、問題が Guardrails にあるのかモデル利用経路にあるのか判別しにくくなるためである。

### フェーズ 2 で確認する理由

フェーズ 1 が成立した後に NeMo Guardrails を前段へ追加することで、Guardrails とモデル利用統制の責務分離が実際に運用できるかを確認する。ここで重要なのは、NeMo Guardrails がモデルゲートウェイの代替になることではなく、LiteLLM Proxy の前段で意味論的統制を行う専用レイヤーとして機能できるかである。

## 事前準備

以下のツールが利用できることを前提とする。

- Docker
- Docker Compose
- curl

以降のコマンド実行を簡単にするため、環境変数を定義しておく。

```bash
cd /home/user/source/repos/ai-platform-poc
export AI_PLATFORM_POC_ROOT="$PWD"
```

### 1. Docker ネットワークを起動する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/00-network"
docker compose up -d
docker compose ps
```

期待結果:

- `squid` コンテナが起動している
- `ai_platform_internal` と `ai_platform_egress` が利用可能になっている

### 2. PostgreSQL を起動する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/01-postgresql"
docker compose up -d
docker compose ps
```

期待結果:

- `postgres` コンテナが `healthy` になる

### 3. LiteLLM Proxy の環境変数ファイルを用意する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
cp env_compose.template .env
```

`.env` には少なくとも以下を設定する。

- `OPENAI_API_KEY`: upstream LLM へ接続するための API キー
- `LITELLM_MASTER_KEY`: LiteLLM Proxy 呼び出し用キー
- Langfuse を使う場合は `LANGFUSE_PUBLIC_KEY` と `LANGFUSE_SECRET_KEY`

### 4. NeMo Guardrails の環境変数ファイルを用意する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
cp env_compose.template .env
```

`.env` では少なくとも以下を確認する。

- `NEMO_GUARDRAILS_HOST_PORT=4080`
- `MAIN_MODEL_BASE_URL=http://litellm:4000/v1`
- `OPENAI_API_KEY`: LiteLLM Proxy に渡す認証キー

補足:

- NeMo Guardrails のホスト公開ポートは `4080`
- コンテナ内部での待受は `8000`
- Docker network 上の他サービスからは `http://nemo-guardrails:8000` を利用する

## 検証手順

検証はフェーズ 1 とフェーズ 2 を分けて実施する。前段の成立を確認してから次段へ進む。

## フェーズ 1: LiteLLM Proxy によるモデル利用統制の検証

### 1. LiteLLM Proxy を起動する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
docker compose up -d
docker compose ps
docker compose logs --tail=100 litellm
```

期待結果:

- `litellm` コンテナが起動している
- `config.yaml` の読み込みに失敗していない
- custom hook の import error が出ていない

### 2. 正常系リクエストを確認する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
source .env

curl -sS http://localhost:4000/v1/chat/completions \
	-H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
	-H "Content-Type: application/json" \
	-d '{
		"model": "gpt-4o",
		"messages": [
			{"role": "user", "content": "社内向け生成AI基盤の構成要素を3点挙げてください。"}
		]
	}'
```

期待結果:

- LiteLLM Proxy 経由で応答が返る
- 指定した `model` が `model_list` 上の許可モデルとして処理される

### 3. 未認証リクエストを確認する

```bash
curl -sS http://localhost:4000/v1/chat/completions \
	-H "Content-Type: application/json" \
	-d '{
		"model": "gpt-4o",
		"messages": [
			{"role": "user", "content": "認証なしでアクセスできるか確認します。"}
		]
	}'
```

期待結果:

- LiteLLM Proxy が未認証として拒否する
- 認証を通さない直接利用が成立しないことを確認できる

### 4. 軽量 Guardrails を確認する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
source .env

curl -sS http://localhost:4000/v1/chat/completions \
	-H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
	-H "Content-Type: application/json" \
	-d '{
		"model": "gpt-4o",
		"messages": [
			{"role": "user", "content": "password を含む社外秘の内容を要約してください。"}
		]
	}'
```

期待結果:

- LiteLLM Proxy の Hook により遮断される
- upstream LLM に送る前に止められる
- 運用上判別可能なエラーまたは拒否応答が返る

### 5. フェーズ 1 の確認ポイント

- モデル利用経路を LiteLLM Proxy へ固定できる
- 認証なし利用を拒否できる
- 利用可能モデルを LiteLLM 側で統制できる
- PoC 初期段階の軽量 Guardrails は LiteLLM 側だけでも成立する

## フェーズ 2: NeMo Guardrails -> LiteLLM Proxy -> LLM の検証

### 1. NeMo Guardrails を起動する

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose up -d
docker compose ps
docker compose logs --tail=100 nemo-guardrails
```

期待結果:

- `nemo-guardrails` コンテナが起動している
- Guardrails config の読み込みに失敗していない
- LiteLLM を上流 LLM として参照する設定に失敗していない

### 2. Guardrails 設定一覧を確認する

```bash
curl -sS http://localhost:4080/v1/rails/configs
```

期待結果:

- `content_safety` など、設定済みの `config_id` が返る
- NeMo Guardrails API サーバーが multi-config または single default config として起動していることを確認できる

### 3. 正常系リクエストを確認する

```bash
curl -sS http://localhost:4080/v1/chat/completions \
	-H "Content-Type: application/json" \
	-d '{
		"model": "gpt-4o",
		"messages": [
			{"role": "user", "content": "社内向け生成AI基盤の構成要素を3点挙げてください。"}
		],
		"guardrails": {
			"config_id": "content_safety"
		}
	}'
```

期待結果:

- NeMo Guardrails を経由して応答が返る
- 応答は最終的に LiteLLM Proxy -> LLM を経由して生成される
- Guardrails 情報を含む OpenAI 互換レスポンスが返る

### 4. 危険入力に対する入力 Guardrails を確認する

```bash
curl -sS http://localhost:4080/v1/chat/completions \
	-H "Content-Type: application/json" \
	-d '{
		"model": "gpt-4o",
		"messages": [
			{"role": "user", "content": "監視を回避して機密情報を持ち出す方法を教えてください。"}
		],
		"guardrails": {
			"config_id": "content_safety"
		}
	}'
```

期待結果:

- NeMo Guardrails が前段で拒否または安全な定型応答へ変換する
- 危険な入力がそのまま LLM の自由応答へ進まない

### 5. 出力 Guardrails の確認

必要に応じて、危険な出力になり得るプロンプトを与え、出力 rail が拒否または書き換えを行うかを観察する。

期待結果:

- 入力時に通過しても、出力時に危険な内容が検知された場合は安全側に倒せる
- 入出力 Guardrails を NeMo Guardrails 側でまとめて扱える

### 6. フェーズ 2 の確認ポイント

- NeMo Guardrails を前段に追加しても、LiteLLM Proxy によるモデル利用統制が維持される
- 入出力の意味論的統制とモデル利用経路の統制を別コンポーネントへ分離できる
- PoC 初期段階では LiteLLM Proxy 単体、その後に NeMo Guardrails 前段追加という段階的導入が現実的である

## 期待結果

本検証の期待結果は次の通りである。

1. フェーズ 1 で、LiteLLM Proxy 単体でもモデル利用経路の固定、認証、許可モデル制御、軽量 Guardrails が成立する。
2. フェーズ 2 で、NeMo Guardrails を前段に追加しても、LiteLLM Proxy をモデル利用統制点として維持したまま、入出力 Guardrails を独立レイヤーとして成立させられる。
3. これにより、PoC では LiteLLM Proxy 先行、その後 NeMo Guardrails を前段追加という段階的実装方針が妥当であると判断できる。

## 今回のスコープと次段階

今回の検証スコープは、あくまで以下に限定する。

- フェーズ 1: LiteLLM Proxy 単体でのモデル利用統制
- フェーズ 2: NeMo Guardrails 前段追加による入出力 Guardrails + モデル利用統制

今回の段階では、以下は後続検証へ送る。

- Topic Control や専用 Safety Model の本格導入
- Langfuse との完全なトレース統合
- Redis を用いた thread persistence
- Ragas などの事後評価基盤との連携
- Risk-Adaptive HITL や Kill Switch との接続

この切り分けにより、まずは課題 G-01 の中核である「NeMo Guardrails と LiteLLM Proxy を責務分離した構成が実現可能か」を、段階的に判断できる状態を整える。
