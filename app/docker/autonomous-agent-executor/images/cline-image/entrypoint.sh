#!/bin/bash
set -e

# 1. Firewallの初期化 (sudoが必要)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "🛡️ Initializing Firewall..."
    sudo /usr/local/bin/init-firewall.sh
fi

# 2. 作業ディレクトリの権限チェック（マウントされた場合用）
sudo chown -R codeuser:codeuser /workspace

# 環境変数がある場合のみ認証を実行
if [ -n "$LLM_API_KEY" ]; then
  cline auth -p "$LLM_PROVIDER" -k "$LLM_API_KEY" -b "$LLM_BASE_URL" -m "$LLM_MODEL"
fi
# その後に本来のコマンドを実行 
if [ -t 0 ]; then
  exec "$@"
else
  exec "$@" < /dev/null
fi