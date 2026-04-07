# ai-platform-poc

業務適用を見据えた生成AI基盤の PoC リポジトリです。単に AI アプリを試作するのではなく、生成AI を企業システムとして成立させるために、責務分離、統制、監査、非同期運用まで含めて検証することを目的としています。

本 PoC では、Application層、Tool層、AIガバナンス層の 3 層を中核に据え、周辺実行基盤を含めた全体構成を検討し、実装と技術検証を進めています。

## このリポジトリが扱うこと

従来の業務システムでは取り込みにくかった、非定型データ処理、探索的調査、例外判断、人間承認を伴う業務を、説明可能かつ統制可能な形でシステム化することを狙います。主な論点は次のとおりです。

- Application層で、どこまでを固定フローにし、どこからを AI に委譲するか
- Tool層で、外部システム接続をどう標準化し、どう安全に扱うか
- AIガバナンス層で、入出力統制、予算統制、評価、監査、停止判断をどう組み込むか
- API Gateway、BFF、Event Bus、状態管理DB、Checkpointer、Observability を含めて、実運用可能な配置にどう落とすか

## アーキテクチャの考え方

### 3 層の責務

| 層 | 役割 |
| --- | --- |
| Application層 | AI の推論、計画、業務フロー制御を担う「脳」 |
| Tool層 | DB、SaaS、ファイル、社内システムとの接続を担う「手足」 |
| AIガバナンス層 | 入出力統制、根拠性、評価、監査、停止判断を担う「免疫・関所」 |

この 3 層は責務による分類です。実際の運用では、これに加えて API Gateway、BFF、Event Bus、状態管理DB、Checkpointer、Observability 基盤などの補助コンポーネントが必要です。

### Application層の型

本 PoC では、制御フローの委譲度に応じて次の 3 類型を扱います。

- WF型: 予見可能な固定フローを中心に処理する型
- SV型: スーパーバイザーと人間承認を組み合わせて統制する型
- 自律型: 探索的タスクをサンドボックス内で段階的に自律化する型

## リポジトリ構成

| パス | 役割 |
| --- | --- |
| app/ai-platform-samplelib | PoC 用ライブラリ群。BFF、OIDC、MCP、イベント連携などのサンプル実装 |
| docs | アーキテクチャ検討、実現方式、検証計画、検証結果をまとめた主文書群 |
| infra | Docker Compose ベースの周辺基盤。Proxy、DB、Redis、LiteLLM、NeMo Guardrails、Langfuse、Dify、Zitadel など |
| tmp | 作業用・一時検証用のワークスペース |

## まず読むドキュメント

設計レビューの入口としては、次の順で読むと全体像を掴みやすくなります。

1. [docs/01_アーキテクチャ検討/00_はじめに.md](docs/01_アーキテクチャ検討/00_はじめに.md)
2. [docs/01_アーキテクチャ検討/01_AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md](docs/01_アーキテクチャ検討/01_AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md)
3. [docs/02_アーキテクチャ実現方式/01_生成AI基盤のコンポーネント配置と実装・運用原則.md](docs/02_アーキテクチャ実現方式/01_生成AI基盤のコンポーネント配置と実装・運用原則.md)
4. [docs/03_検証準備/00_全体方針.md](docs/03_検証準備/00_全体方針.md)
5. [docs/11_技術課題検証/00_検証文書台帳.md](docs/11_技術課題検証/00_検証文書台帳.md)
6. [docs/21_検証結果/01_生成AI基盤インフラ構築手順.md](docs/21_検証結果/01_生成AI基盤インフラ構築手順.md)

個別レイヤの詳細を見たい場合は、次を参照してください。

- Application層: [docs/01_アーキテクチャ検討/02_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md](docs/01_アーキテクチャ検討/02_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)
- Tool層: [docs/01_アーキテクチャ検討/03_AIエージェントの業務適用を見据えた生成AIツール層の検討.md](docs/01_アーキテクチャ検討/03_AIエージェントの業務適用を見据えた生成AIツール層の検討.md)
- AIガバナンス層: [docs/01_アーキテクチャ検討/04_AIエージェントの業務適用を見据えた生成AIガバナンス層の検討.md](docs/01_アーキテクチャ検討/04_AIエージェントの業務適用を見据えた生成AIガバナンス層の検討.md)

## 検証ハイライト

技術課題の検証は [docs/11_技術課題検証/00_検証文書台帳.md](docs/11_技術課題検証/00_検証文書台帳.md) で一覧化しています。現時点では、次の論点で具体的な前進があります。

- WF型 LangGraph 実装では、workflow 実装テスト、Coordinator 入口、durable workflow の承認待ち到達を確認
- WF型 LangGraph 実装では、workflow 実装テスト、workflow backend 入口、durable workflow の承認待ち到達を確認
- SV型 LangGraph 実装では、approval 停止制御の修正後に、paused 遷移と deep_agent 分岐の live 再確認を実施
- 自律型コーディングエージェント呼び出しでは、API / CLI の両方で process backend 起動を確認
- 入出力 Guardrails とモデル利用統制では、LiteLLM と NeMo Guardrails による遮断挙動を確認
- インフラ系では、network、PostgreSQL、Redis、Langfuse、NeMo Guardrails など主要 Compose の起動と復旧を順次確認

検証状況の正式な最新値は、必ず台帳と各検証文書を参照してください。

## セットアップの入口

詳細な構築手順は [docs/21_検証結果/01_生成AI基盤インフラ構築手順.md](docs/21_検証結果/01_生成AI基盤インフラ構築手順.md) を参照してください。README では入口だけ示します。

### 前提ツール

- Docker / Docker Compose
- Git
- uv

### まず起動対象になる基盤

最小限の確認では、次の順で基盤を立ち上げる想定です。

1. infra/00-network
2. infra/01-postgresql
3. infra/11-redis
4. infra/02-litellm
5. infra/03-nemo-guardrails
6. 必要に応じて infra/12-langfuse、infra/22-dify、infra/91-zitadel など

### 設定方針

- 非秘匿の設定値は config.yml で管理する
- 秘匿情報は .env または実環境変数で管理する
- コンポーネントごとの詳細設定は各ディレクトリ配下の文書やテンプレートを参照する

局所的な手順の例:

- OIDC サンプル: [app/ai-platform-samplelib/src/ai_platform_samplelib/oidc/README.md](app/ai-platform-samplelib/src/ai_platform_samplelib/oidc/README.md)
- NeMo Guardrails: [infra/03-nemo-guardrails/README.md](infra/03-nemo-guardrails/README.md)

## この README のスコープ

この README は、リポジトリ全体の位置づけと導線を示すためのものです。以下はここでは扱いません。

- 各 Docker Compose の詳細起動手順
- すべての環境変数一覧
- 各検証文書の全文要約
- 個別モジュールの API 仕様

必要に応じて、上記の既存文書を参照してください。