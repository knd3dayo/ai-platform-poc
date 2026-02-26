#!/bin/bash
# 環境変数がある場合のみ認証を実行
if [ -n "$CLINE_API_KEY" ]; then
  cline auth -p "$CLINE_API_PROVIDER" -k "$CLINE_API_KEY" -b "$CLINE_API_BASE_URL" -m "$CLINE_MODEL_ID"
fi
# その後に本来のコマンドを実行
exec "$@"