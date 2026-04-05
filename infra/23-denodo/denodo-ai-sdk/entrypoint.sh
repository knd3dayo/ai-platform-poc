#!/bin/sh
set -eu

# 1. Firewallの初期化 (スクリプトが存在する場合のみ)
if [ -f "/usr/local/bin/init-firewall.sh" ]; then
    echo "Initializing Firewall..."
    # Preserve env vars.
    /usr/local/bin/init-firewall.sh
fi

# UID/GID の指定は docker-compose.yml の user: で行う想定。
if [ "$#" -eq 0 ]; then
    set -- /bin/bash
fi

exec "$@"
