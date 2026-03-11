#!/bin/sh
  # envファイルの読み込み。
  set -a
  . ./env_run
  set +a

# テストクライアントの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate

# Executor MCP サーバ（host-side python process）を起動してからSVを実行
python -m ai_platform_samplelib.application.autonomous.mcp.mcp_server --mode http --host 127.0.0.1 --port 5001 >/tmp/executor-mcp.log 2>&1 &
MCP_PID=$!
trap 'kill "$MCP_PID" >/dev/null 2>&1 || true' EXIT

# 起動待ち（簡易）
sleep 1

python -m ai_platform_samplelib.application.super_visor.cli.main run -y -s . "/workspace/test_client.sh の内容を日本語で説明して。"
