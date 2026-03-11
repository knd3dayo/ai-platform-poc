#!/bin/sh
# AI_PLATFORM_POC_ROOT が未設定 / 不正な場合はエラー
if [ -z "$AI_PLATFORM_POC_ROOT" ]; then
  echo "❌ AI_PLATFORM_POC_ROOT is not defined. Please set it to the root directory of the project."
  exit 1
fi

if [ ! -d "$AI_PLATFORM_POC_ROOT" ]; then
  echo "❌ AI_PLATFORM_POC_ROOT does not exist or is not a directory: $AI_PLATFORM_POC_ROOT"
  exit 1
fi

# envファイルの読み込み。
set -a
. ./env_run
set +a

# 第1引数： cline または claude
if [ "$1" = "cline" ]; then
  echo "🚀 Starting Cline ..."
  # cline を使用する場合の例
  export COMPOSE_COMMAND="cline -y"

elif [ "$1" = "claude" ]; then
  echo "🚀 Starting Claude ..."
  # claudeを使用する場合の例
  export COMPOSE_COMMAND="claude --dangerously-skip-permissions -p"

elif [ "$1" = "opencode" ]; then
  echo "🚀 Starting Open Code ..."
  # opencodeを使用する場合の例
  export COMPOSE_COMMAND="opencode run"

else
  echo "❌ Invalid argument. Use 'cline', 'claude', or 'opencode'."
  exit 1
fi


# テストクライアントの起動スクリプト
. ${AI_PLATFORM_POC_ROOT}/app/ai-platform-samplelib/.venv/bin/activate
PROMPT=${2:-"test_client.sh スクリプトを日本語で説明して。"}
python -m .main run -s . -s ${CODE_AGENT_CONFIG_PATH} "$PROMPT"