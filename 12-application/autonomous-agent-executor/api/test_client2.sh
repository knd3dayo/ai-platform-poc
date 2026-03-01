#!/bin/sh

AI_PLATFORM_LIB=../../../ai-platform-samplelib

# テストクライアントの起動スクリプト
. ${AI_PLATFORM_LIB}/.venv/bin/activate
python -m ai_platform_samplelib.application.autonomous.test_client.client2
