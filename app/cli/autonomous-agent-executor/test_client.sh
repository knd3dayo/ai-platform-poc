#!/bin/sh
# AI_PLATFORM_POC_ROOTが定義されていない場合はエラー
if [ -z "$AI_PLATFORM_POC_ROOT" ]; then
  echo "❌ AI_PLATFORM_POC_ROOT is not defined. Please set it to the root directory of the project."
  exit 1
fi

# envファイルの読み込み。
set -a
. ./.env
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
python -m ai_platform_samplelib.application.autonomous.cli.main run -s . test_client.shスクリプトを日本語で説明して。 