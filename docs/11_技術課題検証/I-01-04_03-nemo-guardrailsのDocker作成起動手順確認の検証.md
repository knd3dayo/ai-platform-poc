# I-01-04_03-nemo-guardrailsのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-04「`03-nemo-guardrails` の Docker 作成・起動手順確認」について、NeMo Guardrails を前段ガードレール用コンポーネントとして起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-04 | NeMo Guardrails の compose 資材と設定ディレクトリで起動できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-04 に対応し、`infra/03-nemo-guardrails` の起動手順を確認する。
- [../../infra/03-nemo-guardrails/docker-compose.yml](../../infra/03-nemo-guardrails/docker-compose.yml)
  - 実際の compose 定義を確認する。
- [../../infra/03-nemo-guardrails/README.md](../../infra/03-nemo-guardrails/README.md)
  - 設定前提と起動方法を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- NeMo Guardrails コンテナが起動し、設定ディレクトリを参照できること。

### 2. 異常系

- 停止時にサービス提供が継続しないこと。
- 設定不足時にログから原因を確認できること。

### 3. 運用系

- rails 設定更新後の再起動手順を説明できること。
- LiteLLM など前後段との関係を説明できること。

## 前提条件

- Docker / Docker Compose が利用可能であること。
- Guardrails の設定ファイル群が配置済みであること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

期待結果:

- `docker compose config -q` が成功する。
- 対象サービスが running で表示される。
- 初期化失敗を示す致命的エラーがログに出ていない。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose stop
docker compose ps
docker compose start
```

期待結果:

- 停止中は running サービスが減少し、復旧手順で再開できる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | NeMo Guardrails の compose 資材と設定ディレクトリで起動できる。 |
| 制御成立性 | 停止・再開時の状態変化を把握できる。 |
| 運用成立性 | 設定更新と再起動の手順を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | OK | `docker compose config -q` は成功した。`docker compose up -d --build` により `nemo-guardrails` は healthy で起動し、`GET /v1/rails/configs` は `[{"id":"content_safety"}]` を返した。`OPENAI_API_KEY` を LiteLLM の Virtual Key (`sk-poc-master-key-12345`) に合わせた後は、LiteLLM の alias 名 `poc-chat-model` を参照する設定で `POST /v1/chat/completions` も HTTP 200 で通常応答した。 |
| 異常系 | OK | `docker compose stop` 実行中は `curl http://localhost:4080/v1/rails/configs` が `curl: (7) Failed to connect to localhost port 4080` で失敗した。設定不足を模した `nemoguardrails server --config=/missing --port=8000` では `/missing` に対する `FileNotFoundError` がログに出力され、原因を特定できた。 |
| 運用系 | OK | `docker compose start` / `docker compose restart` 後に `GET /v1/rails/configs` は再度成功した。`configs` 配下の設定更新は `docker compose restart` で反映できる。`OPENAI_API_KEY` にはクライアント向けのキーではなく、NeMo Guardrails から LiteLLM へ接続するための Virtual Key を設定する必要がある。危険入力では alias 名 `poc-chat-model` を使った呼び出しでも `I can't assist with that request.` を返すことを確認した。 |

## 検証メモ

### 1. クライアント実装上の考慮事項

- NeMo Guardrails はクライアント API 認証を標準機能として強く持っておらず、インターネット公開や BFF 越し利用では前段 Proxy や拡張ヘッダーでの補完を前提に設計する必要がある。
- Colang の State を使う場合、クライアントは `thread_id` を生成・保持し、会話継続中は同一値を送り続ける必要がある。
- そのため、OpenAI 互換 API として見えていても、クライアント実装は完全透過にはならず、セッション管理や認証境界の設計を別途考慮する必要がある。
- LiteLLM を前段に置く場合も、NeMo Guardrails 側は実モデル名ではなく LiteLLM の alias 名を参照する方が、モデル差し替え時の影響を局所化できる。
- `infra/03-nemo-guardrails/configs/content_safety/config.yml` の `model` は `poc-chat-model` に変更し、通常入力・危険入力の双方で alias 経由の動作を確認した。

### 2. NeMo Guardrails と LiteLLM Proxy の比較

| 比較項目 | NeMo Guardrails Server | LiteLLM Proxy (Hooks / Guardrails) |
| --- | --- | --- |
| 主な設計思想 | プログラマブルな対話制御（シナリオ制御） | LLM ゲートウェイ（認証・管理・集約） |
| クライアント互換性 | 一部改修が必要。`thread_id` 管理などを考慮する必要がある。 | OpenAI SDK 互換で、そのまま使いやすい。 |
| 認証 (API Key) | 組み込みは限定的。前段 Proxy や拡張ヘッダー等で補完を検討する。 | Virtual Key、利用制限、上流キー隠蔽を標準で扱いやすい。 |
| 対話状態 (State) | 維持可能。文脈に応じた段階制御ができる。 | 原則リクエスト単位。会話全体を跨ぐ制御は不得意。 |
| Colang (シナリオ) | フル活用可能。対話の遷移を強制できる。 | 非対応。単発の検査・書き換えが中心。 |
| ストリーミング | 出力検査を有効にすると一括返却寄りになりやすい。 | 入力検査後にそのままストリーミングしやすい。 |
| 複数 LLM 管理 | 単一 config 内での管理が中心で、動的切替は複雑になりやすい。 | モデル抽象化、冗長化、フォールバックが得意。 |
| パフォーマンス | 内部での意図判定やフロー制御分のオーバーヘッドがある。 | 比較的軽量で、高スループットに向く。 |
| ログ・監視 | デバッグログ中心。 | Langfuse などとの連携を組み込みやすい。 |
| 実装難易度 | 高い。Colang 学習、State 設計、クライアント調整が必要。 | 比較的低い。設定と Hook 実装中心で進めやすい。 |

### 3. 実装・運用で事前に見ておくべき点

#### NeMo Guardrails を採用する場合

- 認証 Proxy の構築コストを見込むこと。公開 API 化するなら Nginx や BFF など前段の責務設計が必要になる。
- `thread_id` の採番、保持、再送をクライアント実装に組み込むこと。
- State 永続化が必要な場合は Redis 等の別途準備を見込むこと。
- 出力ガードを厳密にすると、ChatGPT 的な逐次ストリーミング体験は弱くなる前提で UX 合意を取ること。

#### LiteLLM Proxy を採用する場合

- 文脈依存の制御は弱く、会話全体のシナリオ逸脱防止は基本的に担えない前提で使うこと。
- 標準機能外の Guardrails を入れる場合は `custom_callbacks` 実装コストが発生すること。
- クライアントには実モデル名ではなく、LiteLLM 側のエイリアス名を使わせる運用に寄せること。

### 4. 採用判断メモ

- 一般的な API 互換性、認証、モデル集約、監視連携だけを重視するなら LiteLLM Proxy の方が扱いやすい。
- 一方で、金融、医療、社内規程のように「絶対にシナリオから外したくない」要件では、Colang によって会話の主導権を LLM から切り離せる点が重要である。
- そのため、NeMo Guardrails はクライアント実装上の制約があるものの、規制業務や厳格な業務フロー誘導が必要な領域では採用候補として継続検討する。

### 5. シナリオ逸脱防止が必要な業務の例

- 金融業務: 投資勧誘では、免責表示やリスク許容度確認を完了しない限り具体的商品名を出さないように制御できる。
- 医療業務: 症状入力を検知したら診断を禁止し、定型の受診勧奨と病院案内フローへ強制分岐できる。
- 社内規程案内: 副業、経費、勤怠などの問い合わせを、最新規程や申請フローへの誘導に固定し、一般論での誤回答を抑制できる。

## 残課題

- LiteLLM 前段配置の接続試験は成立したが、NeMo Guardrails を生成AIシステムアーキテクチャの標準的なガードレール機能として採用するかどうかは継続検討とする。
- 継続検討の理由として、クライアントから見た API キー認証がダミー化しやすいこと、Colang 利用時にクライアントが `thread_id` を意識する必要があることなど、運用・実装の扱いづらさがある。
- rails ごとの振る舞い差分や、他のガードレール実装との比較評価は本手順確認の対象外とする。