#!/bin/sh


mkdir -p /srv/ai_platform/workspaces/e2e_ws_1

task_id=$(curl -sS -X POST http://localhost:7101/execute \
	-H 'Content-Type: application/json' \
	-d '{"prompt":" opencode.jsoncを確認して、このワークスペースで利用可能なMCPツール一覧を表示してください。ワークスペース直下に done.txt を作ってMCPツール一覧を書いてください","workspace_path":"/srv/ai_platform/workspaces/e2e_ws_1","timeout":300}' \
	| python3 -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')

echo "task_id=$task_id"

# 完了までポーリング（sub_status が completed/failed/... になるまで）
while true; do
	curl -sS "http://localhost:7101/status/${task_id}?tail=80" | python3 -c '
import json,sys

raw = sys.stdin.read().strip()
if not raw:
    print("(empty response)")
    raise SystemExit(1)

try:
    s = json.loads(raw)
except json.JSONDecodeError:
    print("(non-json response)")
    print(raw[:200])
    raise SystemExit(1)

print("status=", s.get("status"), "sub_status=", s.get("sub_status"))
if s.get("status") == "exited" and s.get("sub_status") in ("completed", "failed", "timeout", "cancelled"):
    raise SystemExit(0)
raise SystemExit(1)
'
	if [ $? -eq 0 ]; then break; fi
	sleep 2
done

curl -sS "http://localhost:7101/status/${task_id}?tail=80" 

ls -la /srv/ai_platform/workspaces/e2e_ws_1
cat /srv/ai_platform/workspaces/e2e_ws_1/done.txt
