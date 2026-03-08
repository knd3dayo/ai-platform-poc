FROM python:3.12-slim

# 1. 必要なツールのインストール (Firewall制御用ツールを追加)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    sudo \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. ユーザー作成 (ユーザー名:denodo、グループ:denodoで作成。UID、GIDは実行時に設定)
# NOTE: Debian系では useradd が同名グループを自動作成する場合があるため、存在チェック付きで作成する。
RUN set -eux; \
    if ! getent group denodo >/dev/null; then groupadd -r denodo; fi; \
    if ! id -u denodo >/dev/null 2>&1; then useradd -m -s /bin/bash -g denodo denodo; fi

#################################
# denodoの作業
#################################
USER denodo

WORKDIR /home/denodo

# 3. git cloneでdenodo-ai-sdkをクローン
RUN git clone https://github.com/denodo/denodo-ai-sdk.git

# 4. 作業ディレクトリをdenodo-ai-sdkに移動
WORKDIR /home/denodo/denodo-ai-sdk
## tag public_v013 をチェックアウト
RUN git switch -d public_v013

# 5. venvの作成と有効化、依存関係のインストール
RUN python -m venv venv && \
    . venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt
    
USER root

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/bin/bash"]