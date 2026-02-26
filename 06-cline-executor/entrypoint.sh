#!/bin/bash
# 環境変数がある場合のみ認証を実行
if [ -n "$MY_API_KEY" ]; then
  cline auth -p "$CLINE_API_PROVIDER" -k "$MY_API_KEY" -b "$MY_BASE_URL" -m "$MY_MODEL"
fi
# その後に本来のコマンドを実行
exec "$@"