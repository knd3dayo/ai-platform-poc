#!/bin/bash
set -e

# 1. Firewallの初期化 (sudoが必要)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "🛡️ Initializing Firewall..."
    sudo /usr/local/bin/init-firewall.sh
fi

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

# 3. USER_IDとGROUP_IDを環境変数から取得して、codeuserのUIDとGIDを変更
if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
    echo "🔧 Setting codeuser UID to $USER_ID and GID to $GROUP_ID"
    sudo usermod -u "$USER_ID" codeuser
    sudo groupmod -g "$GROUP_ID" codeuser
    # 変更後のUIDとGIDで作業ディレクトリの所有権を再設定
    sudo chown -R codeuser:codeuser /workspace
fi

if [ -t 0 ]; then
    exec runuser -u codeuser -- "$@"
else
    exec runuser -u codeuser -- "$@" < /dev/null
fi