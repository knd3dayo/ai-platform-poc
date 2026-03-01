#!/bin/sh

# .envファイルの読み込み
set -a
. ./.env
set +a

# APIサーバーの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate
python -m ai_platform_samplelib.application.autonomous.api.main

