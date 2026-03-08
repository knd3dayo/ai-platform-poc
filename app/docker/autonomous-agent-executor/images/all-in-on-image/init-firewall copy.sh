#!/bin/bash
set -euo pipefail

# Egress制御: Dockerネットワーク（コンテナが所属するサブネット）宛のみ許可し、
# それ以外のアウトバウンド通信を遮断する。

echo "🛡️ Applying egress firewall rules (Docker-network-only)..."
echo "🧪 init-firewall.sh revision: dev-20260308-1"

if ! command -v iptables >/dev/null 2>&1; then
	echo "iptables is not available" >&2
	exit 1
fi

primary_iface="$(ip -o route show default 2>/dev/null | awk '{print $5; exit}')"
if [ -z "${primary_iface}" ]; then
	primary_iface="$(ip -o link show | awk -F': ' '$2 != "lo" {print $2; exit}')"
fi

if [ -z "${primary_iface}" ]; then
	echo "Could not determine primary network interface" >&2
	exit 1
fi

docker_cidr="$(ip -o -4 addr show dev "${primary_iface}" | awk '{print $4; exit}')"
if [ -z "${docker_cidr}" ]; then
	echo "Could not determine IPv4 CIDR for interface: ${primary_iface}" >&2
	exit 1
fi

# Filterテーブルのルールをクリア
iptables -F
iptables -X

# 基本ポリシー
iptables -P INPUT ACCEPT
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# ループバック（DockerのDNS: 127.0.0.11 等）
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -d 127.0.0.0/8 -j ACCEPT

# 既存コネクション
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Dockerネットワーク内のみ許可（例: ai_platform_net のサブネット）
iptables -A OUTPUT -d "${docker_cidr}" -j ACCEPT

# opencode web は UI 資産を https://app.opencode.ai へプロキシするため、
# egress 制限下でも最低限の TCP/443 を許可する必要がある。
# ドメインは起動時に解決し、その IP のみに限定して許可する。
if [ "${ALLOW_OPENCODE_APP_EGRESS:-}" = "true" ] || [ "${ALLOW_OPENCODE_APP_EGRESS:-}" = "1" ]; then
	app_host="${OPENCODE_APP_HOST:-app.opencode.ai}"
	if command -v getent >/dev/null 2>&1; then
		app_ips="$(getent ahostsv4 "${app_host}" 2>/dev/null | awk '{print $1}' | sort -u)"
	else
		app_ips=""
	fi

	if [ -z "${app_ips}" ]; then
		echo "⚠️  Could not resolve ${app_host}; opencode web asset proxy may fail." >&2
	else
		for ip in ${app_ips}; do
			iptables -A OUTPUT -p tcp -d "${ip}" --dport 443 -j ACCEPT
		done
		echo "✅ Allowed opencode web egress to ${app_host}:443 (${app_ips})"
	fi
fi

# それ以外は「DROP」ではなく「REJECT」で即時失敗させる。
# DROP だと TCP の connect() が SYN 再送で長時間ブロックし、SYN-SENT が残りやすい。
# REJECT にするとアプリ側は即座にエラー（例: ECONNREFUSED/EHOSTUNREACH）になり切り分けしやすい。
iptables -A OUTPUT -p tcp -j REJECT --reject-with tcp-reset
iptables -A OUTPUT -p udp -j REJECT --reject-with icmp-port-unreachable
iptables -A OUTPUT -j REJECT --reject-with icmp-host-unreachable

echo "✅ Firewall rules applied. Allowed egress: 127.0.0.0/8, ${docker_cidr} (via ${primary_iface})"