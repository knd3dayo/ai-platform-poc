#!/bin/bash
set -e

# PATH の最終確認
export PATH=$PATH:/home/clineuser/.npm-global/bin

# 環境変数がある場合のみ認証を実行
if [ -n "$LLM_API_KEY" ]; then
  cline auth -p "$LLM_PROVIDER" -k "$LLM_API_KEY" -b "$LLM_BASE_URL" -m "$LLM_MODEL"
fi
# その後に本来のコマンドを実行 
exec "$@" < /dev/null