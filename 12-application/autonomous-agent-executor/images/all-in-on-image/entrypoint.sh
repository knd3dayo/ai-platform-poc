#!/bin/bash
set -e

# 1. Firewallの初期化 (sudoが必要)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "🛡️ Initializing Firewall..."
    sudo /usr/local/bin/init-firewall.sh
fi

# 2. 環境変数をopencode.jsonに反映させるためのPythonスクリプトを実行
mkdir -p /home/codeuser/.config/opencode
python3 /home/codeuser/create_opencode_json.py  /home/codeuser/.config/opencode/opencode.json

# 3. USER_IDとGROUP_IDを環境変数から取得して、codeuserのUIDとGIDを変更
if [ -n "$USER_ID" ] && [ -n "$GROUP_ID" ]; then
    echo "🔧 Setting codeuser UID to $USER_ID and GID to $GROUP_ID"
    sudo usermod -u "$USER_ID" codeuser
    sudo groupmod -g "$GROUP_ID" codeuser
    # 変更後のUIDとGIDで作業ディレクトリの所有権を再設定
    sudo chown -R codeuser:codeuser /workspace
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

# 環境変数がある場合のみ認証を実行
if [ -n "$LLM_API_KEY" ]; then
  echo "⚠️ LLM_API_KEY is not set. Skipping cline authentication."
  exit 1
fi
if [ -n "$LLM_PROVIDER" ]; then
  echo "⚠️ LLM_PROVIDER is not set. Skipping cline authentication."
  exit 1
fi
if [ -n "$LLM_MODEL" ]; then
  echo "⚠️ LLM_MODEL is not set. Skipping cline authentication."
  exit 1
fi
if [ -n "$LLM_BASE_URL" ]; then
    cline auth -p "$LLM_PROVIDER" -k "$LLM_API_KEY" -m "$LLM_MODEL" -b "$LLM_BASE_URL"
else
    cline auth -p "$LLM_PROVIDER" -k "$LLM_API_KEY" -m "$LLM_MODEL"
fi

if [ -t 0 ]; then
    exec runuser -u codeuser -- "$@"
else
    exec runuser -u codeuser -- "$@" < /dev/null
fi