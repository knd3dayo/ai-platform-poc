#!/bin/bash
# 基本的なアウトバウンド制限の例
# 必要に応じて、LLMのAPIエンドポイントへの許可設定を追加してください

# 全てのルールをクリア
iptables -F
iptables -X

# 基本ポリシー: 全て許可（ここから制限を強めていく）
iptables -P OUTPUT ACCEPT

# 例: ローカルネットワーク(192.168.x.x)へのアクセスを禁止する場合
# iptables -A OUTPUT -d 192.168.0.0/16 -j REJECT

echo "✅ Firewall rules applied."