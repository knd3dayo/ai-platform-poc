#!/bin/sh
# 第1引数： cline または claude
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
elif [ "$1" = "open-code" ]; then
  echo "🚀 Starting Open Code API Server..."
    # envファイルの読み込み。
    set -a
    . ./.env_open_code
    set +a
else
  echo "❌ Invalid argument. Use 'cline', 'claude', or 'open-code'."
  exit 1
fi


# テストクライアントの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate
python -m ai_platform_samplelib.application.autonomous.cli.main run -s . test_client.shスクリプトを日本語で説明して。 