FROM node:22-slim

# 1. 必要なツールのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. ユーザー作成 (UIDを1000に合わせるとホスト側との権限トラブルが減ります)
# nodeユーザーと衝突しないよう、既存のnodeユーザーを削除するか、UIDを調整します
RUN userdel -r node && \
    useradd -m -u 1000 clineuser

# 3. 作業ディレクトリの作成と権限変更
WORKDIR /workspace
RUN chown clineuser:clineuser /workspace

# 4. Clineのインストール先パス設定
ENV NPM_CONFIG_PREFIX=/home/clineuser/.npm-global
ENV PATH=$PATH:/home/clineuser/.npm-global/bin

COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]

USER clineuser

# 5. Clineのインストール
RUN mkdir -p /home/clineuser/.npm-global && \
    npm install -g cline

CMD ["/bin/bash"]