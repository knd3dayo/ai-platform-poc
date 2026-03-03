#!/bin/bash
set -e

# 1. Firewallの初期化 (sudoが必要)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "🛡️ Initializing Firewall..."
    sudo /usr/local/bin/init-firewall.sh
fi

# 2. 作業ディレクトリの権限チェック（マウントされた場合用）
sudo chown -R codeuser:codeuser /workspace

# claude CLI が参照する環境変数にマッピング（compose の ${VAR} 展開に依存しない）
if [ -z "${ANTHROPIC_AUTH_TOKEN}" ] && [ -n "${LLM_API_KEY}" ]; then
    export ANTHROPIC_AUTH_TOKEN="${LLM_API_KEY}"
fi
if [ -z "${ANTHROPIC_BASE_URL}" ] && [ -n "${LLM_BASE_URL}" ]; then
    export ANTHROPIC_BASE_URL="${LLM_BASE_URL}"
fi
if [ -z "${ANTHROPIC_MODEL}" ] && [ -n "${LLM_MODEL}" ]; then
    export ANTHROPIC_MODEL="${LLM_MODEL}"
fi


exec "$@" < /dev/null