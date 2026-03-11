#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)

WS_BASE=/srv/ai_platform/workspaces
WS_NAME=e2e_sv_ws_1
WS_PATH="$WS_BASE/$WS_NAME"

mkdir -p "$WS_PATH"
rm -f "$WS_PATH/done.txt"

# Ensure the shared docker network exists (compose files expect it).
if ! docker network inspect ai_platform_internal >/dev/null 2>&1; then
  docker network create ai_platform_internal >/dev/null
fi

# Default LLM settings (override by exporting env vars before running this script).
: "${LLM_PROVIDER:=openai}"
: "${LLM_MODEL:=gpt-4o}"
: "${LLM_API_KEY:=sk-poc-master-key-12345}"
# NOTE: This is used inside containers; prefer the Docker network hostname.
: "${LLM_BASE_URL:=http://litellm:4000}"
# Passed through to executor containers as well.
: "${LLM_BASE_URL_IN_CONTAINER:=$LLM_BASE_URL}"

export LLM_PROVIDER LLM_MODEL LLM_API_KEY LLM_BASE_URL LLM_BASE_URL_IN_CONTAINER

# Optionally build image (SKIP_BUILD=1 to skip).
if [ "${SKIP_BUILD:-}" != "1" ]; then
  (cd "$REPO_ROOT/app/docker/super-visor/images/sv-cli-dood" && docker compose build super-visor-cli)
fi

# Run Super-Visor CLI in a DoOD container; it will start executor containers via docker.sock.
(
  cd "$REPO_ROOT/app/docker/super-visor/images/sv-cli-dood" && \
  docker compose run --rm \
    -e HOST_UID="$(id -u)" \
    -e HOST_GID="$(id -g)" \
    super-visor-cli \
    run -y -s "$WS_PATH" \
    "このワークスペース直下に done.txt を新規作成し、1行目に 'OK' とだけ書いてください。完了したら done.txt の内容を表示して終了してください。"
)

# Validate artifacts
if [ ! -f "$WS_PATH/done.txt" ]; then
  echo "done.txt was not created: $WS_PATH/done.txt" >&2
  exit 1
fi

echo "=== workspace ==="
ls -la "$WS_PATH"

echo "=== done.txt ==="
cat "$WS_PATH/done.txt"
