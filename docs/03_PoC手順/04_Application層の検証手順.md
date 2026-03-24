## 初期段階
### Zitadel Bearerトークン連携の検証

目的: クライアントが ZITADEL で OAuth 認証を行って access token を取得し、BFF が Bearer token を受けて検証したうえで下流 backend に転送し、backend 側でも認証・認可に利用できることを確認します。

前提:
- ZITADEL が `http://localhost:8080` で起動していること
- service account の Access Token Type が `JWT` であること
- service account key JSON が利用可能であること
- `app/ai-platform-samplelib/src/ai_platform_samplelib/oidc/.env` に `OIDC_TEST_APPLICATION_KEY_PATH` が設定済みであること

ターミナル1（backend 起動）:

```bash
cd /home/user/source/repos/ai-platform-poc/app/ai-platform-samplelib
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.backend_server --port 5802
```

ターミナル2（BFF 起動）:

```bash
cd /home/user/source/repos/ai-platform-poc/app/ai-platform-samplelib
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.server --port 5801
```

ターミナル3（client から BFF を呼び出し）:

```bash
cd /home/user/source/repos/ai-platform-poc/app/ai-platform-samplelib

# Bearer token を取得し、BFF で検証
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.client --path /protected/me --print-token

# BFF から backend に Bearer token を転送
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.client --path /protected/forward/backend
```

期待値:
- `/protected/me` が `200` を返す
- `/protected/forward/backend` が `200` を返す
- backend 側で subject / client_id / audience が取得できる

backend 認可の確認（任意）:

```bash
access_token=$(PYTHONPATH=src .venv/bin/python - <<'PY'
import asyncio
from ai_platform_samplelib.oidc.client import fetch_access_token

async def main():
	response = await fetch_access_token()
	print(response['access_token'])

asyncio.run(main())
PY
)

curl -sS http://localhost:5802/backend/authorize/client \
	-H "Authorization: Bearer ${access_token}"
```

role / custom claim 認可の確認（任意）:
- `app/ai-platform-samplelib/src/ai_platform_samplelib/oidc/config.yml` の `authorization.required_project_roles` に要求ロールを設定する
- `authorization.required_claim_values` に必要な custom claim を設定する
- backend の以下の endpoint で検証する
  - `/backend/authorize/role`
  - `/backend/authorize/claims`

ZITADEL 側の設定ポイント:
- Project で role を作成する
- Role Assignments で対象 principal に role を付与する
- Project Settings で role assertion を有効にする
- 必要に応じて Application Token Settings で User Roles inside ID Token を有効にする
- custom claim は Actions の complement token flow で追加する

`config.yml` の設定例:

```yaml
authorization:
	allowed_client_ids:
		- login-client
	required_project_roles:
		- admin
	project_role_claim_keys:
		- urn:zitadel:iam:org:project:roles
		- urn:zitadel:iam:org:project:365171666990530564:roles
	required_claim_values:
		department:
			- sales
```

期待値:
- role claim または custom claim が token に入っていない場合、対応する backend endpoint は `403` を返す
- 必要な値を満たす token で再実行すると `200` を返す

### 自律型エージェントの検証

#### （開発用）MCP（FastMCP）での疎通（BFFなし）
* BFF抜き、自律型エージェントはサブプロセス、ワークスペースはホスト上のパス、BearerとトレースIDはダミー

目的: MCPサーバとして executor を起動し、テスト用 FastMCP クライアントから `healthz/execute/status/cancel` を呼び出して疎通確認します。

前提:
- `ai-platform-samplelib` の依存関係が導入済みであること（例: `cd ${AI_PLATFORM_LIB} && uv sync`）
- workspace は「ホスト上の絶対パス」を指定すること（例: `/srv/ai_platform/workspaces/...` or `/tmp/...`）
- Bearer と trace id はダミーでOK（ヘッダ伝搬の疎通確認）

ターミナル1（MCPサーバ起動 / streamable-http）:

```bash
cd ${AI_PLATFORM_LIB}

# executor の backend は env で選択
export AI_PLATFORM_TASK_BACKEND=subprocess
export AI_PLATFORM_SUBPROCESS_COMMAND='bash -lc'

# 既存の 7101/7102 と衝突しない例
uv run -m ai_platform_samplelib.application.autonomous.mcp.mcp_server \
	--mode http --host 127.0.0.1 -p 7111
```

ターミナル2（テスト用 FastMCP クライアント実行）:

```bash
cd ${AI_PLATFORM_LIB}

workspace_path=/srv/ai_platform/workspaces/ws_mcp_subprocess_1
mkdir -p "$workspace_path"
chown -R "$(id -u)":"$(id -g)" "$workspace_path" 2>/dev/null || sudo chown -R "$(id -u)":"$(id -g)" "$workspace_path"

# ツール一覧（任意）
uv run -m autonomous_agent_util._test_.mcp_client \
	--url http://127.0.0.1:7111/mcp \
	--list-tools

# healthz（任意）
uv run -m autonomous_agent_util._test_.mcp_client \
	--url http://127.0.0.1:7111/mcp \
	--healthz

# execute → status 収束まで待つ（E2E）
uv run -m autonomous_agent_util._test_.mcp_client \
	--url http://127.0.0.1:7111/mcp \
	--header 'Authorization: Bearer dummy' \
	--header 'X-Trace-Id: trace-dummy-001' \
	--workspace-path "$workspace_path" \
	--prompt 'sleep 1; echo hello > hello.txt' \
	--wait --tail 50
```

キャンセル検証（任意）:

```bash
uv run -m autonomous_agent_util._test_.mcp_client \
	--url http://127.0.0.1:7111/mcp \
	--workspace-path "$workspace_path" \
	--prompt 'sleep 30; echo hello > hello.txt' \
	--wait --cancel-after 1
```

NOTE:
- `bash -lc` の場合、prompt に外側の引用符を付けないでください（例: `--prompt 'sleep 1; echo hello > hello.txt'` はOK）。
- MCPサーバ側のツール名が環境により `execute` ではなく `execute_async/execute_sync` になる場合がありますが、テストクライアント側は自動フォールバックします。

--
未整備
--
### LangGraphによるSV型エージェント（Textual TUI）

初期段階クライアント（BFF抜き）として、Textual のTUIから HITL（承認/スキップ/一時停止）を操作できます。

```bash
cd ${AI_PLATFORM_LIB}

# 必須: LLM 接続設定（例）
# - OpenAI 直の場合は LLM_BASE_URL は不要
# - LiteLLM Proxy を使う場合は LLM_BASE_URL を指定
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export LLM_API_KEY=sk-poc-master-key-12345
export LLM_BASE_URL=http://localhost:4000

# 初回 / 依存更新時のみ
# uv sync

uv run -m ai_platform_samplelib.application.super_visor.tui.app
```

操作（最小）:
- Setup画面で `Message`（指示）を入力し、必要なら `Source dirs` にホストパスをカンマ区切りで指定して `Run`
- 計画が表示されたら `y`（開始）/ `n`（中止）
- サブタスクごとに `a`（承認して実行）/ `s`（スキップ）/ `p`（一時停止）
- `p` で停止した場合、ログにセッションJSONのパスが出るので、Setup画面の `Resume from` に貼り付けて `Resume`

NOTE:
- `trace_id` は画面上部に表示され、pause/resume でも維持されます（セッションJSONにも保存されます）。


### LangGraphによるSV型エージェント（CLI）

SV型エージェントは、いったんAPIではなくCLIで検証します。

```bash
cd "$AI_PLATFORM_POC_ROOT/test/application/super-visor"
./test_client.sh cline 2>&1 | tee /tmp/sv_cli_smoke.log
```

CLI版
```bash
cd ${AI_PLATFORM_LIB}
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export LLM_API_KEY=sk-your-key
# export LLM_BASE_URL=http://localhost:4000
uv run -m ai_platform_samplelib.application.super_visor.cli.main run \
	-s "$AI_PLATFORM_POC_ROOT" \
	"このプロジェクトを日本語で説明して"
```



## （開発用）subprocess backend での検証（Docker不要）

Docker（DoOD）を起動せずに、ホスト上の Python subprocess で自律型タスクを実行します。

### 前提

- `ai-platform-samplelib` の依存関係が導入済みであること（例: `cd ${AI_PLATFORM_LIB} && uv sync`）
- 共有workspace（例）: `/srv/ai_platform/workspaces`

### 実行（detach で起動 → status で収束確認）

```bash
cd ${AI_PLATFORM_LIB}

# backend は import 時に決まるため、TaskService を import する前に env を設定してください
export AI_PLATFORM_TASK_BACKEND=subprocess
export AI_PLATFORM_SUBPROCESS_COMMAND='bash -lc'

uv run python - <<'PY'
import asyncio
from ai_platform_samplelib.application.autonomous.core.task_service import TaskService
from ai_platform_samplelib.application.autonomous.core.task_manager import TaskManager
from ai_platform_samplelib.application.autonomous.core.abstract_actions import AbstractActions
from ai_platform_samplelib.application.autonomous.model.models import TaskStatus

class Actions(AbstractActions):
	def after_start_task_action(self, tid: str) -> None: print('started', tid)
	def after_start_detach_task_action(self, tid: str) -> None: print('detached', tid)
	async def progress_action(self, tid: str) -> TaskStatus:
		return await TaskManager.get_status(tid, tail=10)
	def after_complete_action(self, runner) -> None: print('complete')
	def after_task_not_found_action(self) -> None: pass
	def after_list_action(self, table: list) -> None: pass
	def after_cancel_action(self, task_id: str) -> None: pass
	def after_get_status_action(self, task_id: str, status_data: TaskStatus) -> None: pass
	def prune_progress_action(self, generator): pass

async def main():
	task_id = 'subprocess-smoke-1'
	# IMPORTANT: bash -lc の場合、prompt に外側の引用符を付けないでください
	#   NG: '"echo hello > hello.txt"'（文字列全体が「1つのコマンド名」扱いになりやすい）
	#   OK: 'echo hello > hello.txt'
	await TaskService.run(
		actions=Actions(),
		task_id=task_id,
		prompt='sleep 1; echo hello > hello.txt',
		sources=None,
		timeout=60,
		wait=False,
	)

	for _ in range(20):
		st = await TaskManager.get_status(task_id, tail=10)
		print('poll', st.status, st.sub_status)
		if st.status == 'exited':
			print('artifacts', st.artifacts)
			return
		await asyncio.sleep(0.5)

asyncio.run(main())
PY
```

補足:
- `AI_PLATFORM_TASK_BACKEND` は `TaskService` import 後に変更しても反映されません（import 時に backend 実装が選択されます）。
- subprocess backend は `stdout` / `stderr` / `exit_code` をファイルへ永続化するため、detach（`wait=False`）でも `status` 取得時に `exited completed/failed` へ収束できます。

### （開発用）subprocess backend を API として起動して検証する（curl）

同じ `/execute` / `/status` API を、ホスト上の subprocess backend で動かして検証します。

```bash
cd ${AI_PLATFORM_LIB}

export AI_PLATFORM_TASK_BACKEND=subprocess
export AI_PLATFORM_SUBPROCESS_COMMAND='bash -lc'

# DoOD bundle とポートが衝突しないよう、開発用は 7102 を推奨
uv run -m ai_platform_samplelib.application.autonomous._api_.api_server -p 7102

# 補足: 同期（テスト用途）で検証したい場合は --sync_mode を付ける
# - /execute がタスク完了までブロックする
# - 返却時点で status は exited completed/failed に収束している想定
uv run -m ai_platform_samplelib.application.autonomous._api_.api_server -p 7102 --sync_mode
```

別ターミナルで実行:

```bash
workspace_path=/srv/ai_platform/workspaces/ws_api_subprocess_1
mkdir -p "$workspace_path"
chown -R "$(id -u)":"$(id -g)" "$workspace_path" 2>/dev/null || sudo chown -R "$(id -u)":"$(id -g)" "$workspace_path"

task_id=$(curl -sS -X POST http://localhost:7102/execute \
	-H 'content-type: application/json' \
	-d "$(python - <<'PY'
import json
print(json.dumps({
	# IMPORTANT: bash -lc の場合、prompt に外側の引用符を付けない
	'prompt': 'sleep 1; echo hello > hello.txt',
	'workspace_path': '/srv/ai_platform/workspaces/ws_api_subprocess_1',
	'timeout': 60,
}))
PY
)" \
	| python - <<'PY'
import json, sys
print(json.load(sys.stdin)['task_id'])
PY
)

# 補足: APIサーバを --sync_mode で起動している場合、/execute は完了までブロックするため
# `time curl ...` にすると待ち時間（sleep等）が分かりやすい。

echo "task_id=${task_id}"
curl -sS "http://localhost:7102/status/${task_id}?tail=50"
```

## 備考（実装中）: Docker関連の検証（最終段階）

以降は「最終段階（コンテナによるサンドボックス化 / DoOD など）」の手順です。
初期段階の検証が終わった後に参照してください。

### コーディングエージェント用Sandboxの構築

このリポジトリでは、executor（Sandbox）イメージは `docker-compose.yml` 側で `build:` を行わず、各イメージディレクトリの `build.sh` で事前に `docker build` します。

- 目的: `ai-platform-samplelib` をイメージに含めるため（ビルドコンテキスト外は `COPY` できないため、`build.sh` が一時的に build context 配下へコピーします）
- 前提: `images/*/.env` の `AI_PLATFORM_LIB` が正しいパスを指していること（デフォルトは `../../../../ai-platform-samplelib`）

```bash
cd "$AI_PLATFORM_POC_ROOT/app/docker/autonomous-agent-executor/images/all-in-on-image"

# 初回のみ（必要に応じて編集）
cp -n .env_template .env

# イメージを事前ビルド（docker compose build は不要）
./build.sh
```

テスト:

```bash
./run.sh opencode run "このプロジェクトを日本語で説明して"
```

### ワンセットDoOD（bundle）での検証（推奨: PoC）

SV + 自律型 executor API を同居させた bundle コンテナを起動し、bundle から `docker.sock` を通して executor コンテナを起動します（DoOD: Docker outside of Docker）。

前提:

- 共有 workspace ルート（PoC 固定）: `/srv/ai_platform/workspaces`
- bundle の API ポート: `7101`
- bundle がホストの Docker daemon を操作するため、`/var/run/docker.sock` をマウントします

必要に応じて、ホスト側で workspace を作成しておきます。

```bash
sudo mkdir -p /srv/ai_platform/workspaces
sudo chown -R "$(id -u)":"$(id -g)" /srv/ai_platform/workspaces
```

起動（通常モード）:

```bash
cd "$AI_PLATFORM_POC_ROOT/app/docker/autonomous-agent-executor/images/one-set-dood"

# bundle を起動（HOST_UID/HOST_GID は、成果物の owner をホストユーザーに寄せるため）
HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose up -d --build --force-recreate

# ヘルスチェック
curl -sS http://localhost:7101/healthz
```

E2E（/execute → /status）:

```bash
cd $AI_PLATFORM_POC_ROOT/test/application/autonomous
./test_dood.sh
```

手動実行（curl）:

`/execute` で起動し、`/status` をポーリングして完了（`status=exited`）を確認します。

```bash
workspace_path=/srv/ai_platform/workspaces/ws_api_1
mkdir -p "$workspace_path"
chown -R "$(id -u)":"$(id -g)" "$workspace_path" 2>/dev/null || sudo chown -R "$(id -u)":"$(id -g)" "$workspace_path"

task_id=$(curl -sS -X POST http://localhost:7101/execute \
	-H 'content-type: application/json' \
	-d "$(python - <<'PY'
import json
print(json.dumps({
	'prompt': 'このプロジェクトを日本語で説明して',
	'workspace_path': '/srv/ai_platform/workspaces/ws_api_1',
	'timeout': 300,
}))
PY
)" \
	| python - <<'PY'
import json, sys
print(json.load(sys.stdin)['task_id'])
PY
)

echo "task_id=${task_id}"

for i in $(seq 1 60); do
	body=$(curl -sS "http://localhost:7101/status/${task_id}?tail=20")
	echo "$body" | python - <<'PY'
import json, sys
o=json.load(sys.stdin)
print('status', o.get('status'), 'sub_status', o.get('sub_status'))
PY
	echo "$body" | python - <<'PY'
import json, sys
o=json.load(sys.stdin)
print('stdout_tail:\n' + (o.get('stdout') or ''))
PY
	echo "$body" | python - <<'PY'
import json, sys
o=json.load(sys.stdin)
if o.get('status') == 'exited':
	raise SystemExit(0)
raise SystemExit(1)
PY
	if [ $? -eq 0 ]; then
		break
	fi
	sleep 2
done

# キャンセル（必要な場合）
# curl -sS -X DELETE "http://localhost:7101/cancel/${task_id}"
```

### （開発用）entrypoint.sh / init-firewall.sh を bind マウントして検証する

executor 側の `entrypoint.sh` / `init-firewall.sh` を調整したい場合、開発用 override を使うと executor イメージを rebuild しなくても変更を反映できます。

重要: DoOD では bind マウント元パスは「ホスト基準」で解釈されます。
そのため bundle コンテナ内で参照するリポジトリパス（`HOST_REPO_ROOT`）を、ホストと同じ絶対パスでミラーリングして見せる必要があります。

```bash
cd "$AI_PLATFORM_POC_ROOT/app/docker/autonomous-agent-executor/images/one-set-dood"

# HOST_REPO_ROOT は「ホスト上のこのリポジトリの絶対パス」を指定
HOST_REPO_ROOT="$AI_PLATFORM_POC_ROOT" \
HOST_UID=$(id -u) HOST_GID=$(id -g) \
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build --force-recreate
```

このモードでは、executor 起動時に

- `$AI_PLATFORM_POC_ROOT/app/docker/autonomous-agent-executor/images/all-in-on-image/init-firewall.sh`
- `$AI_PLATFORM_POC_ROOT/app/docker/autonomous-agent-executor/images/all-in-on-image/entrypoint.sh`

がコンテナへ bind マウントされるため、スクリプト変更のたびに executor イメージを rebuild する必要がありません。

### CLIでコーディングエージェント用コンテナを起動するテストクライアント

- 配置場所: `test/application/autonomous-agent-executor`
- 事前に `AI_PLATFORM_POC_ROOT` をこのリポジトリのルートに設定しておく

```bash
cd "$AI_PLATFORM_POC_ROOT/test/application/autonomous-agent-executor"

# 初回のみ（必要に応じて編集）
cp -n .env_template .env

# 実行例（利用するエージェントを選ぶ）
./test_client.sh [cline|claude|opencode]
```

### Docker（DoOD）版（SV CLIをコンテナ化して実行）
```bash
# 前提: executor イメージが事前ビルド済みであること
cd "$AI_PLATFORM_POC_ROOT/app/docker/autonomous-agent-executor/images/all-in-on-image"
./build.sh

# SV CLI コンテナ
cd "$AI_PLATFORM_POC_ROOT/app/docker/super-visor/images/sv-cli-dood"

# LLM設定はホスト環境からコンテナへ引き継ぎます（必要なものだけ export）
# 例: infra/05-litellm を起動済みなら、ネットワーク内の別名で到達できることが多いです
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export LLM_API_KEY=sk-poc-master-key-12345
export LLM_BASE_URL=http://litellm:4000

# 共有workspace（ホスト基準の絶対パス）を指定して実行する
mkdir -p /srv/ai_platform/workspaces/sv_ws_1
# 権限で失敗する場合のみ sudo を付けてください
chown -R "$(id -u)":"$(id -g)" /srv/ai_platform/workspaces/sv_ws_1 2>/dev/null || sudo chown -R "$(id -u)":"$(id -g)" /srv/ai_platform/workspaces/sv_ws_1

# 実行（成果物 owner をホストユーザーに寄せたい場合は HOST_UID/GID を付与）
HOST_UID=$(id -u) HOST_GID=$(id -g) \
docker compose run --rm -it super-visor-cli run -y -s /srv/ai_platform/workspaces/sv_ws_1 \
	"このプロジェクトを日本語で説明して"
```

NOTE:
- DoODでは executor コンテナ側の bind mount パスは「ホスト基準」で解釈されます。`-s` は `/srv/ai_platform/workspaces/...` のようなホスト絶対パス（共有workspace）を推奨します。
- `LLM_BASE_URL` を `http://localhost:...` にすると、Docker版ではSVコンテナ内の localhost を指します。LiteLLM を使う場合は `http://litellm:4000` のように network alias を指定するのが安全です。
