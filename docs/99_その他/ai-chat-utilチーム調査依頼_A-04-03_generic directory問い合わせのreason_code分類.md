# ai-chat-util チーム調査依頼: generic な directory 問い合わせの reason_code 分類をどう扱うべきか

## 想定する issue タイトル

structured routing で generic な local directory 問い合わせが `general_tool_agent` に入る場合の reason_code をどう分類するべきか整理したい

## 概要

A-04-03 の approval 停止制御は、現在は `general_tool_agent -> analyze_files -> paused` で live に安定確認できている。

一方で、generic な `work ディレクトリを確認してください` 問い合わせでは、route 自体は期待どおり `general_tool_agent` に入っているにもかかわらず、reason code が `route.explicit_directory_path_request` ではなく `route.general_tool_sufficient` 系に分類されている。

route 揺れ自体は再現しなくなったため、現在の論点は不具合というより routing ラベル設計・分類仕様の整理である。

## 背景

- 対象検証: A-04-03 SV 型 LangGraph 独自実装の検証
- 既に確認できていること:
  - approval 停止制御の最小修正後、`general_tool_agent -> analyze_files` 経路では deterministic に `paused` へ収束する
  - absolute path を含む local directory 問い合わせは `route.explicit_directory_path_request` で安定する
  - deep investigation 要求は `deep_agent` に分岐する

今回の論点は `paused` 収束そのものではなく、generic directory 問い合わせの route 理由ラベルをどう定義するべきかである。

## 実測結果

### ケース 1: generic な local directory 問い合わせ

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリを確認してください"
```

実測結果:

- trace_id: `f0a4abbe22ad4e40b67b62a9b88c03ff`
- `route_decision_model_output.selected_route: general_tool_agent`
- `route_decision_model_output.reason_code: route.directory_check`
- `route_decided.route_name: general_tool_agent`
- `route_decided.reason_code: route.general_tool_sufficient`
- `tool_selected.tool_name: analyze_files`
- `tool_result_received.reason_code: hitl.tool_approval_required`
- `final_status: paused`

評価:

- route と最終状態の観点では期待どおり
- ただし reason code は explicit-directory 系ではない

### ケース 2: absolute path を含む local directory 問い合わせ

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work ディレクトリを確認してください"
```

実測結果:

- trace_id: `3ac7c869887d4012afa6525889d50187`
- `route_decided.route_name: general_tool_agent`
- `route_decided.reason_code: route.explicit_directory_path_request`
- `tool_selected.tool_name: analyze_files`
- `tool_result_received.reason_code: hitl.tool_approval_required`
- `final_status: paused`

評価:

- absolute path を含む場合は、reason code まで含めて期待どおり

### ケース 3: deep investigation 要求

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリ全体を起点に深く調査してください"
```

実測結果:

- trace_id: `23695bee2d404b4fb8ba5f217b619f4d`
- `route_decided.route_name: deep_agent`
- `route_decided.reason_code: route.multi_step_investigation_needed`
- `final_status: completed`

評価:

- 単発 directory 確認要求と deep investigation の境界は機能している

## 問題意識

- generic な directory 問い合わせは route と最終状態の観点では正しい経路へ入っている
- そのため、route 選択アルゴリズム自体を変えたいわけではない
- 一方で、監査ログや受け入れ基準を reason code まで見る場合、generic 問い合わせが `route.explicit_directory_path_request` に揃わないため、仕様解釈がぶれる

## 確認したいこと

1. generic な `work ディレクトリを確認してください` を `route.general_tool_sufficient` と分類する現行挙動は意図どおりか
2. `route.directory_check` / `route.general_tool_sufficient` と `route.explicit_directory_path_request` の使い分け仕様はどう定義しているか
3. `working_directory` 配下で解決できる directory 名だけを与えたケースは、explicit-directory 系へ寄せる方が監査上分かりやすいか
4. reason code を変更する場合、routing prompt の表現修正で十分か、それとも post-processing / 正規化が必要か
5. 受け入れ基準としては、route と最終状態だけ一致していれば十分か、reason code まで固定すべきか

## 期待する回答

- 現行仕様としての reason_code 分類方針
- 現状を仕様として受け入れるか、ラベルを調整するかの判断
- 必要なら最小修正方針

## 関連文書

- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-04-03_SV型LangGraph独自実装の検証.md`
- `/home/user/source/repos/ai-platform-poc/docs/99_その他/ai-chat-utilチーム調査依頼_完了_A-04-03_workディレクトリ問い合わせのroute揺れ.md`
