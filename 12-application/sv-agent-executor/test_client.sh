#!/bin/sh

# .envファイルの読み込み
set -a
. ./.env
set +a

# テストクライアントの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate
python -m ai_platform_samplelib.application.super_visor.test_client.client --api-url http://localhost:7201 --message 'hello from client' --max-wait-sec 30 2>&1