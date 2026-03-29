#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LITELLM_ENV_FILE="${LITELLM_ENV_FILE:-$POC_ROOT/infra/02-litellm/.env}"
AI_CHAT_UTIL_ROOT="${AI_CHAT_UTIL_ROOT:-/home/user/source/repos/ai-chat-util/app}"

if [[ ! -f "$LITELLM_ENV_FILE" ]]; then
  echo "env file not found: $LITELLM_ENV_FILE" >&2
  exit 1
fi

extract_env_value() {
  local key="$1"
  local value

  value="$(grep -E "^${key}=" "$LITELLM_ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
  if [[ -z "$value" ]]; then
    echo "required key not found in $LITELLM_ENV_FILE: $key" >&2
    exit 1
  fi

  printf '%s' "$value"
}

export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-$(extract_env_value LITELLM_MASTER_KEY)}"
export LLM_API_KEY="${LLM_API_KEY:-$(extract_env_value LLM_API_KEY)}"

cd "$AI_CHAT_UTIL_ROOT"
exec uv run -m ai_chat_util.cli "$@"