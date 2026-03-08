#!/bin/sh
  # envファイルの読み込み。
  set -a
  . ./env_run
  set +a

# テストクライアントの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate
python -m ai_platform_samplelib.application.super_visor.cli.main run -y -s . "/workspace/test_client.sh の内容を日本語で説明して。"
