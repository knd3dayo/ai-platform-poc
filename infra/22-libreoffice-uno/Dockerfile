FROM debian:bookworm-slim

# ビルド引数の定義（デフォルト値として1000を設定）
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN apt-get update && apt-get install -y --no-install-recommends\
    python3 \
    python3-pip \
    python3-uno \
    libreoffice \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \
    fastapi \
    python-multipart \
    unoserver \
    uvicorn

COPY src /opt/uno-api/src
COPY run_server.sh /opt/uno-api/run_server.sh

RUN chmod +x /opt/uno-api/run_server.sh

# 指定されたIDでグループとユーザーを作成
# すでにIDが存在する場合のエラーを避けるため、既存チェックを入れるとより堅牢です
RUN groupadd -g ${GROUP_ID} uno || true && \
    useradd -l -u ${USER_ID} -g ${GROUP_ID} -m uno

USER uno
EXPOSE 2003
EXPOSE 2004
ENV PYTHONPATH=/opt/uno-api/src
ENTRYPOINT ["/opt/uno-api/run_server.sh"]