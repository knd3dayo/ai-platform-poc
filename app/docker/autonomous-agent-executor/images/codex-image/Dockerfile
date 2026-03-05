# 1. Node.js 環境をベースにする
FROM node:22-slim

# 2. Codex CLI と依存ツールのインストール
# git: リポジトリのインスペクションに必須
# curl/ca-certificates: Web検索やAPI連携に必須
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    python3 \
    python3-pip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 3. Codex CLI をグローバルにインストール
RUN npm install -g @openai/codex

# 4. 作業ディレクトリの設定
WORKDIR /workspace

# 5. セキュリティ & 設定保持のためのユーザー設定
# Codex CLI は設定を ~/.config に保存するため、ホームディレクトリを確保
RUN useradd -m -u 1001 codexuser

# 6. アプリケーション用ディレクトリとライブラリ配置
ARG AI_PLATFORM_LIB=ai-platform-samplelib
RUN mkdir -p /home/codexuser/app && chown -R codexuser:codexuser /home/codexuser
COPY ${AI_PLATFORM_LIB} /home/codexuser/app
RUN chown -R codexuser:codexuser /home/codexuser/app

USER codexuser

# 7. 初期設定（認証）を保持するためのボリューム
VOLUME ["/home/codexuser/.config"]

# 8. デフォルトコマンド
CMD ["codex"]
