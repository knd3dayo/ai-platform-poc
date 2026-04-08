# A-04-06_自律型DeepAgents実装の検証

## 検証目的

本検証の主目的は、サブ課題 A-04-06「自律型エージェントの実装検証（DeepAgentsによる実装）」について、PoC 環境で成立性を確認することである。

最終的には、A-04 の完了判定に必要な材料として、DeepAgents による自律型構成で、動的計画、サブエージェント利用、停止条件付き実行がどこまで成立するかを明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-04 | A-04-06 | DeepAgents による自律型構成で、動的計画、サブエージェント利用、停止条件付きの実行が成立するかを確認する。 |

必要に応じて、副次的に A-03-02、A-03-03、A-03-04 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/01_技術課題と対応方針.md)
  - A-04-06 に対応し、DeepAgents を自律型基盤として採用できるかを確認する。
- [生成AIアプリケーション層の実現方式](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - 自律型は目標と境界条件のみを与え、思考と行動のループを許容する整理を参照する。
- [02_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md](../01_アーキテクチャ検討/02_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)
  - 自律型の基盤候補として DeepAgents を挙げている。
- `${HOME}/source/repos/ai-chat-util/README_FOR_EXPERTS.md`
  - `run_deepagent_chat` と `deep_agent` route を根拠として参照する。

## 検証で確認したいこと

### 1. 正常系

- DeepAgents を自律型として明示起動できること。
- 動的な調査手順、複数段のツール利用、サブエージェント的な役割分担を扱えること。
- 制約付きのツール公開と停止条件設定を前提に運用できること。

### 2. 異常系

- 停止条件や予算上限なしに無制限ループへ流れないこと。
- 自律型で扱うべきでない副作用タスクを無条件で実行しないこと。
- SV 型内部 route と、standalone 自律型入口の違いを曖昧にしないこと。

### 3. 運用系

- DeepAgents の実行ログ、route 選択、使用ツールを追跡できること。
- 追加依存、allowlist、予算制御を運用設定へ落とせること。
- 自律型の昇格基準とレビュー手順へ接続できること。

## 対象構成

| 観点 | 主な既存実装 / 入口 | 備考 |
| --- | --- | --- |
| 明示入口 | `${HOME}/source/repos/ai-chat-util/README_FOR_EXPERTS.md` に記載の `run_deepagent_chat` | 自律型候補の入口 |
| route 選択 | `type_selection_autonomous_on_explicit_deep_request`、`type_selection_autonomous_on_high_exploration` | `agent_chat` routing 側の自律型選択条件 |
| supervisor 内 route | `deep_agent` route | SV 型内委譲先としても利用 |
| 依存導入 | `uv sync --extra deepagents` | 追加依存 |

## 既存実装と入口の対応づけ

1. 明示入口

- `run_deepagent_chat` は DeepAgents を明示的に起動する入口である。

2. agent_chat routing との関係

- `agent_chat` は明示的な deep request や高探索性を見て自律型候補を選べる。
- その際の backend 候補として DeepAgents を位置付けられる。

3. 現時点の制約

- 実装根拠は README / route 設定 / 追加依存導入に分散している。
- standalone な長時間自律実行の完全な実測結果はまだ整理されていない。

## 前提条件

- `${HOME}/source/repos/ai-chat-util/app` で DeepAgents 追加依存が導入済みであること。
- MCP / LiteLLM / allowlist 対象ツールが利用可能であること。
- 停止条件と予算制御の運用方針が整理されていること。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv sync --extra deepagents
```

### 2. 正常系確認

期待結果:

- DeepAgents を明示起動できる。
- 高探索性の要求を自律型として処理できる。
- 複数段の調査とツール利用が成立する。

### 3. 異常系確認

期待結果:

- 無制限ループや過剰なツール利用を抑止する必要性を明示できる。
- 停止条件未設定のまま本番利用しない前提を確認できる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | DeepAgents を自律型の一実装基盤として位置付ける入口と設定が存在する。 |
| 制御成立性 | 高探索性要求、自律型選択条件、停止条件の必要性を説明できる。 |
| 運用成立性 | 追加依存、allowlist、予算制御、レビュー接続の論点を整理できる。 |

## 検証結果記録欄

### 2026-04-05 実測結果

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/_test_/test_deepagent_entrypoints.py -q
```

実行結果:

- `10 passed in 6.68s`
- 次の観点を確認した。
  - `run_deepagent_chat` の明示入口が存在すること。
  - CLI、API、MCP から DeepAgents 系入口へ到達できること。
  - batch 系の補助入口も同時に公開されること。

補足:

- 自律型として重要な停止条件、予算上限、成果物レビュー接続までは今回の入口テストでは検証していない。
- したがって、DeepAgents を自律型の実装基盤として完全に確認したのではなく、少なくとも明示入口と公開契約が成立している段階を確認した。

### 2026-04-07 仕様変更追随再検証結果

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/_test_/test_deepagent_entrypoints.py -q
```

実行結果:

- `10 passed in 6.49s`
- 次の観点を再確認した。
  - `run_deepagent_chat` の明示入口は引き続き利用可能であること。
  - CLI、API、MCP から DeepAgents 系入口へ到達できること。
  - workflow backend の `agent_chat` 統合後も、DeepAgents 明示入口と batch 系補助入口の公開契約は崩れていないこと。

補足:

- 今回の仕様変更は `coordinated_chat` 廃止と `agent_chat` 統合が中心であり、`run_deepagent_chat` 系の明示入口自体は後方互換影響を受けていない。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 一部確認済み | DeepAgents の明示入口と API / MCP 公開契約をテストで確認した。 |
| 異常系 | 一部確認済み | 明示入口未登録のような基本破綻は確認されなかった。absolute directory path を空または未検出と返した DeepAgents 共通事象は upstream で root cause と修正方針が整理済みであり、PoC 側では修正版取り込み後の再確認が残る。 |
| 運用系 | 一部確認済み | 追加依存と入口契約は確認済み。予算制御とレビュー運用に加え、修正版取り込み後に directory path を concrete target として扱えるかの利用ガイド整備が未確認である。 |

### 2026-04-08 ai-chat-util チーム回答反映

[ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgentsのdirectory path解釈と展開品質.md](../99_その他/ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgentsのdirectory path解釈と展開品質.md) に対する回答では、absolute directory path 問題の主因は DeepAgents 実行経路で `explicit_user_directory_paths` の文脈が不足していたことと整理された。

確認できた点:

- directory expansion 本体ではなく、workflow 作成経路と tool 解決経路への directory 文脈伝播不足が主因
- prompt と sufficiency 判定の双方で、tool evidence の弱い absence claim を補強する修正が入った
- upstream 追試では trace_id `62638961c2e440dda57eade28caa7468` で `analyze_files` が `docs` 配下 20 件を解析し、共通見出し要約まで到達した

本書への含意:

- 自律型 DeepAgents 明示入口でも、従来の「既存 directory を空または未検出と返す」という残課題は、少なくとも今回の absolute path ケースについて原因未解明ではなくなった。
- PoC 側の残件は、修正版 ai-chat-util を取り込んだうえで、自律型入口の同一シナリオを再実測し、内容品質の改善を確認することである。

### 2026-04-08 修正版取り込み後の PoC 再実測

上記残件に対して、修正版 ai-chat-util を取り込んだ現行環境で DeepAgents 明示入口の same scenario を再実行した。

回帰テスト実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/_test_/test_deepagent_entrypoints.py -q
```

実行結果:

- `10 passed in 6.77s`

評価:

- DeepAgents 明示入口の CLI / API / MCP 公開契約は、修正版取り込み後も維持されている。

live 実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  run_deepagent_chat -p "/home/user/source/repos/ai-platform-poc/docs ディレクトリを段階的に調査し、共通見出しの傾向を説明してください"
```

実行結果:

- `trace_id=cdc919bc479b47bb90b513376bd4f67b`
- `route_decided.route_name=deep_agent`
- `route_decided.reason_code=route.multi_step_investigation_needed`
- `route_decided.payload.forced_route=deep_agent`
- `route_decided.payload.explicit_user_directory_paths=["/home/user/source/repos/ai-platform-poc/docs"]`
- `tool_catalog_resolved.payload.tool_agent_names=["deep_agent"]`
- `tool_selected.tool_name=analyze_files`
- `tool_result_received.payload.success=true`
- `final_answer_validated.reason_code=sufficiency.answer_supported_by_evidence`
- `final_status=completed`

評価:

- 自律型明示入口でも absolute directory path が concrete target として伝播し、`analyze_files` 実行結果に基づく要約応答まで到達した。
- 2026-04-07 時点で残していた「自律型入口への反映確認」は、この PoC 再実測で充足した。
- [A-04-04_SV型DeepAgents実装の検証.md](./A-04-04_SV型DeepAgents実装の検証.md) で確認した supervisor 内 route trace_id `cc93fa4661c84c6d8cad0713cb7a746d` との比較では、standalone 明示入口は `forced_route=deep_agent` を持つ一方、SV 型内部 route は `forced_route=null` であり、両者の使い分けも引き続き監査できる。

補足:

- DeepAgents の監査回帰 test については、[ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgents監査回帰testのimport追随.md](../99_その他/ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgents監査回帰testのimport追随.md) への回答で、旧 module path 前提の test 保守ずれが主因と整理され、PoC 側 fresh rerun でも関連 5 テストの再通過を確認した。
- したがって、A-04-06 側で残るのは test 保守ではなく、停止条件・予算上限・成果物レビューの運用基準整理である。

## 残課題

- 停止条件、予算上限は [A-03-02_停止条件と予算上限の検証.md](./A-03-02_停止条件と予算上限の検証.md) で具体化する。
- 成果物レビューのゲートと再現・評価ハーネスは [A-03-03_テスト再現評価ハーネスの検証.md](./A-03-03_テスト再現評価ハーネスの検証.md) で具体化する。
- 本文書では実装基盤の成立性を扱い、モデル能力評価までは扱わない。