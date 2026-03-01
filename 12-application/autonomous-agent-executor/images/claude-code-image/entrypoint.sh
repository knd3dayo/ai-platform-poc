#!/bin/bash
set -e

# 1. Firewallの初期化 (sudoが必要)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "🛡️ Initializing Firewall..."
    sudo /usr/local/bin/init-firewall.sh
fi

# 2. 作業ディレクトリの権限チェック（マウントされた場合用）
sudo chown -R codeuser:codeuser /workspace


exec "$@" < /dev/null