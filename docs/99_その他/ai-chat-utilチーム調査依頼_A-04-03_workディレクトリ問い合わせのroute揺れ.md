# ai-chat-util チーム調査依頼: `work ディレクトリを確認してください` が `deep_agent` に寄る条件の整理

## 想定する issue タイトル

structured routing で generic なディレクトリ調査問い合わせが `general_tool_agent` ではなく `deep_agent` に寄る条件を整理したい

## 背景

A-04-03 の approval 停止制御については、`general_tool_agent -> analyze_files` 経路であれば、tool guard による事前ブロックと `paused` 収束が live でも確認できた。

一方で、同じ structured-routing + HITL 設定でも、問い合わせ文が generic な `work ディレクトリを確認してください` だと、PoC 側 live 追試では `deep_agent` に route し、approval 対象の `general_tool_agent -> analyze_files` 経路に入らなかった。

これは approval 停止修正の不具合というより、routing 条件の問題として切り分けた方がよいため、別 issue として整理する。

## 実測結果

### ケース 1: generic なディレクトリ調査問い合わせ

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリを確認してください"
```

観測結果:

- trace_id: `4343d83097174ac9b16e4815d9a97e27`
- `route_decision_model_output.selected_route: deep_agent`
- `route_decided.route_name: deep_agent`
- `tool_catalog_resolved.tool_agent_names: ["deep_agent"]`
- `sufficiency_judged.reason_code: sufficiency.answer_supported_by_evidence`
- `final_status: completed`

補足:

- この trace では `general_tool_agent` の `analyze_files` に対する approval イベントは出ていない。
- したがって、approval 停止ロジックの検証ケースにはなっていない。

### ケース 2: explicit file path を含む問い合わせ

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "次の Markdown ファイルを確認して検証目的を要約してください: /home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md"
```

観測結果:

- trace_id: `afb42032789e438ebe1293680edfb66d`
- `route_decision_model_output.selected_route: general_tool_agent`
- `route_decided.route_name: general_tool_agent`
- `tool_selected.tool_name: analyze_files`
- `tool_result_received.reason_code: hitl.tool_approval_required`
- `final_status: paused`

補足:

- explicit file path があると `general_tool_agent` へ安定して寄り、approval 停止の期待経路を通った。

## 問題意識

- 現状の route 判定では、generic なディレクトリ調査問い合わせを `deep_agent` 側へ送ることがある。
- その結果、A-04-03 の approval 検証で見たい `general_tool_agent -> analyze_files` 経路を踏まない。
- 利用者目線でも、単純なローカルディレクトリ確認であれば `general_tool_agent` の方が自然に見える可能性がある。

## 確認したいこと

1. structured routing で generic なローカルディレクトリ調査問い合わせが `deep_agent` に寄る判断基準は何か
2. `preferred_coding_route: deep_agent` がローカルファイル調査意図まで強く引っ張っていないか
3. explicit file path の有無以外に、`general_tool_agent` と `deep_agent` を分ける主要特徴量は何か
4. `work ディレクトリを確認してください` のような問い合わせは、本来どちらへ寄せるのが期待仕様か
5. A-04-03 のような approval 検証用途とは別に、routing 品質観点で改善対象にすべきか

## 期待する回答

- 現行仕様としての route 判断理由
- 意図どおりの挙動かどうか
- 必要なら route プロンプトまたはスコアリングの修正方針
- stable に `general_tool_agent` へ寄せる問い合わせ条件の整理

## 関連文書

- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-04-03_SV型LangGraph独自実装の検証.md`
- `/home/user/source/repos/ai-platform-poc/docs/99_その他/ai-chat-utilチーム調査依頼_A-04-03_agent_chat_approval停止制御.md`

## ai-chat-util チーム回答

もっと issue コメント寄りに整理すると、追加の live 確認ケースは次を推奨するとの回答だった。

1. `work ディレクトリを確認してください`
  - 期待: `general_tool_agent`
  - 期待: `reason_code=route.explicit_directory_path_request`
  - 期待: approval 対象設定時は `analyze_files` 経由で `paused`

2. `/abs/path/to/work ディレクトリを確認してください`
  - 期待: 1 と同様に `general_tool_agent`

3. `work ディレクトリ全体を起点に深く調査してください`
  - 期待: これは `deep_agent` に寄る余地を残し、単発確認要求との境界を確認する

受け入れ基準:

- 単発の local directory 確認要求が stable に `general_tool_agent -> analyze_files` 経路へ入り、approval 検証ケースとして再利用できること。

## 2026-04-07 追加再検証結果

ai-chat-util チームが提示した 3 ケースを現行の PoC 環境で再実行したところ、当初の「generic な `work ディレクトリ` 問い合わせが `deep_agent` に寄る」現象は再現しなかった。

### ケース 1: `work ディレクトリを確認してください`

- trace_id: `f0a4abbe22ad4e40b67b62a9b88c03ff`
- `route_decision_model_output.selected_route: general_tool_agent`
- `route_decision_model_output.reason_code: route.directory_check`
- `route_decided.reason_code: route.general_tool_sufficient`
- `tool_selected.tool_name: analyze_files`
- `tool_result_received.reason_code: hitl.tool_approval_required`
- `final_status: paused`

評価:

- route と最終状態の観点では、単発 local directory 確認要求として期待どおり `general_tool_agent -> analyze_files -> paused` へ入った。
- 一方で reason code は、期待されていた `route.explicit_directory_path_request` ではなく、より汎用的な `route.general_tool_sufficient` 系だった。

### ケース 2: `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work ディレクトリを確認してください`

- trace_id: `3ac7c869887d4012afa6525889d50187`
- `route_decided.route_name: general_tool_agent`
- `route_decided.reason_code: route.explicit_directory_path_request`
- `tool_selected.tool_name: analyze_files`
- `tool_result_received.reason_code: hitl.tool_approval_required`
- `final_status: paused`

評価:

- absolute path を明示したケースは、チーム想定どおり explicit-directory 系の reason code と `paused` まで安定して再現した。

### ケース 3: `work ディレクトリ全体を起点に深く調査してください`

- trace_id: `23695bee2d404b4fb8ba5f217b619f4d`
- `route_decided.route_name: deep_agent`
- `route_decided.reason_code: route.multi_step_investigation_needed`
- `sufficiency_judged.reason_code: sufficiency.answer_supported_by_evidence`
- `final_status: completed`

評価:

- 深掘り依頼では `deep_agent` に寄る境界が維持されており、単発確認要求との切り分けは機能している。

## 現時点の整理

- 受け入れ基準の主眼だった「単発の local directory 確認要求が stable に `general_tool_agent -> analyze_files` 経路へ入ること」は、generic 問い合わせと absolute path 問い合わせの両方で概ね満たされた。
- したがって、当初の route 揺れは現行実装では再現せず、approval 検証シナリオとして再利用できる状態まで改善したと判断できる。
- 残る論点は、generic な `work ディレクトリ` 問い合わせの reason code を `route.explicit_directory_path_request` に寄せるべきか、それとも現状の `route.general_tool_sufficient` 系分類を仕様として受け入れるか、というラベル設計寄りの整理である。

## 対応方針

- 本 issue は、route 揺れそのものの不具合調査としては close 候補とする。
- 根拠は、追加再検証で generic 問い合わせ、absolute path 問い合わせの双方が `general_tool_agent -> analyze_files -> paused` を再現し、当初問題としていた「approval 検証経路へ入らない」現象が現行実装では再現しなかったためである。
- 一方で、generic な `work ディレクトリ` 問い合わせの reason code が explicit-directory 系に揃わない点は残るため、必要なら別途「routing ラベル設計 / reason code 設計」の論点として軽量に管理する。
- A-04-03 の固定回帰シナリオには、reason code まで含めて再現性が高い absolute path 問い合わせを採用する。