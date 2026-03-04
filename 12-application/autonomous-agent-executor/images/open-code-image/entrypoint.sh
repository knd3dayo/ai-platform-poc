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

# その後に本来のコマンドを実行 
if [ -t 0 ]; then
    exec runuser -u codeuser -- "$@"
else
    exec runuser -u codeuser -- "$@" < /dev/null
fi