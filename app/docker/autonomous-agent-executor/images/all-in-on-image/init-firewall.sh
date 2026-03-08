#!/bin/bash
set -euo pipefail

echo "🛡️ Applying egress firewall rules (docker-net only + REJECT)..."
echo "🧪 init-firewall.sh revision: dev-20260308-compact"

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || { echo "$1 is not available" >&2; exit 1; }
}

require_cmd iptables
require_cmd ip
require_cmd awk

is_true() {
	case "${1:-}" in
		1|true|TRUE|yes|YES|on|ON) return 0 ;;
		*) return 1 ;;
	esac
}

flush_filter() {
	iptables -F
	iptables -X
}

set_policies() {
	iptables -P INPUT ACCEPT
	iptables -P FORWARD DROP
	iptables -P OUTPUT "$1"
}

# Escape hatch (no restrictions)
if is_true "${ALLOW_ALL_EGRESS:-}"; then
	echo "⚠️  ALLOW_ALL_EGRESS is enabled: allowing all outbound traffic." >&2
	flush_filter
	set_policies ACCEPT
	exit 0
fi

primary_iface="$(ip -o route show default 2>/dev/null | awk '{print $5; exit}')"
[ -n "${primary_iface}" ] || primary_iface="$(ip -o link show | awk -F': ' '$2 != "lo" {print $2; exit}')"
[ -n "${primary_iface}" ] || { echo "Could not determine primary network interface" >&2; exit 1; }

docker_cidr="$(ip -o -4 addr show dev "${primary_iface}" 2>/dev/null | awk '{print $4; exit}')"
[ -n "${docker_cidr}" ] || { echo "Could not determine IPv4 CIDR for interface: ${primary_iface}" >&2; exit 1; }

flush_filter
set_policies DROP

# Allow: loopback + Docker DNS(127.0.0.11) + established + docker subnet
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -d 127.0.0.0/8 -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d "${docker_cidr}" -j ACCEPT

# Reject everything else quickly (avoid SYN retry hangs)
iptables -A OUTPUT -p tcp -j REJECT --reject-with tcp-reset
iptables -A OUTPUT -p udp -j REJECT --reject-with icmp-port-unreachable
iptables -A OUTPUT -j REJECT --reject-with icmp-host-unreachable

echo "✅ Firewall rules applied. Allowed egress: 127.0.0.0/8, ${docker_cidr} (${primary_iface})"