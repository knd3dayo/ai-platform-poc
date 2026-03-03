#!/bin/bash
set -e

# 1. Firewallの初期化 (sudoが必要)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "🛡️ Initializing Firewall..."
    sudo /usr/local/bin/init-firewall.sh
fi

# 2. 作業ディレクトリの権限チェック（マウントされた場合用）
sudo chown -R codeuser:codeuser /workspace

# 3. 環境変数をopencode.jsonに反映させるためのPythonスクリプトを実行
mkdir -p /home/codeuser/.config/opencode
python3 /home/codeuser/create_opencode_json.py  /home/codeuser/.config/opencode/opencode.json

# その後に本来のコマンドを実行 
if [ -t 0 ]; then
    exec "$@"
else
    exec "$@" < /dev/null
fi