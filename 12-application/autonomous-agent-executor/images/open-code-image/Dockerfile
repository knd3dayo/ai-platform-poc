FROM node:22-slim

# 1. 必要なツールのインストール (Firewall制御用ツールを追加)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    sudo \
    iptables \
    ipset \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# 2. ユーザー作成 (既存のnodeユーザーを再利用して名前を変更)
RUN usermod -l codeuser node && \
    groupmod -n codeuser node && \
    usermod -d /home/codeuser -m codeuser

# 3. 作業ディレクトリの作成と権限変更
WORKDIR /workspace
RUN chown codeuser:codeuser /workspace

# 4. OpenCode AIのインストール先パス設定
ENV NPM_CONFIG_PREFIX=/home/codeuser/.npm-global
ENV PATH=$PATH:/home/codeuser/.npm-global/bin:/home/codeuser/.venv-tools/bin

# 5. FirewallスクリプトとEntrypointの配置
COPY init-firewall.sh /usr/local/bin/
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-firewall.sh /usr/local/bin/entrypoint.sh && \
    # codeuserがsudoをパスワードなしで実行できるように設定 (chown等も含む)
    echo "codeuser ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh, /usr/sbin/chown, /usr/bin/chown" > /etc/sudoers.d/codeuser-admin && \
    chmod 0440 /etc/sudoers.d/codeuser-admin

# 6. OpenCode AIのインストール
USER codeuser
RUN mkdir -p /home/codeuser/.npm-global && \
    npm install -g opencode-ai

# 7. アプリケーション用ディレクトリと権限設定
RUN python3 -m venv /home/codeuser/.venv-tools && \
    /home/codeuser/.venv-tools/bin/pip install --no-cache-dir -U pip && \
    /home/codeuser/.venv-tools/bin/pip install --no-cache-dir uv
RUN mkdir -p /home/codeuser/app && chown codeuser:codeuser /home/codeuser/app
COPY --chown=codeuser:codeuser ai-platform-samplelib /home/codeuser/app
RUN cd /home/codeuser/app && uv sync --no-dev

# 8. opencode.json生成用のPythonスクリプトを配置。(entrypoint.shで実行される)
COPY create_opencode_json.py /home/codeuser/

ENTRYPOINT ["entrypoint.sh"]
CMD ["/bin/bash"]