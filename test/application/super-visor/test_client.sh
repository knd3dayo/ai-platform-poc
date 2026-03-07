#!/bin/sh
# 第1引数： cline / claude / opencode
if [ "$1" = "cline" ]; then
  echo "🚀 Starting Cline API Server..."
    # envファイルの読み込み。
    set -a
    . ./.env_cline
    set +a
elif [ "$1" = "claude" ]; then
  echo "🚀 Starting Claude API Server..."
    # envファイルの読み込み。
    set -a
    . ./.env_claude_code
    set +a
elif [ "$1" = "opencode" ]; then
  echo "🚀 Starting OpenCode ..."
    set -a
    . ./.env_opencode
    set +a
else
  echo "❌ Invalid argument. Use 'cline', 'claude', or 'opencode'."
  exit 1
fi

# テストクライアントの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate
python -m ai_platform_samplelib.application.super_visor.cli.main run -y -s . "/workspace/test_client.sh の内容を日本語で説明して。"
