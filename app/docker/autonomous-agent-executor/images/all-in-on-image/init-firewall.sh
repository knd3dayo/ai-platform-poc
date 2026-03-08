#!/bin/bash
set -euo pipefail

# Egress制御: Dockerネットワーク（コンテナが所属するサブネット）宛のみ許可し、
# それ以外のアウトバウンド通信を遮断する。

echo "🛡️ Applying egress firewall rules (Docker-network-only)..."

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

echo "✅ Firewall rules applied. Allowed egress: 127.0.0.0/8, ${docker_cidr} (via ${primary_iface})"