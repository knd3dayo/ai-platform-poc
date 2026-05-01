FROM python:3.12-slim

# ビルド引数の定義（デフォルト値として1000を設定）
ARG USER_ID=1000
ARG GROUP_ID=1000

RUN apt-get update && apt-get install -y --no-install-recommends\
    libreoffice \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir unoserver

# 指定されたIDでグループとユーザーを作成
# すでにIDが存在する場合のエラーを避けるため、既存チェックを入れるとより堅牢です
RUN groupadd -g ${GROUP_ID} uno || true && \
    useradd -l -u ${USER_ID} -g ${GROUP_ID} -m uno

USER uno
EXPOSE 2003
ENTRYPOINT ["unoserver", "--addr", "0.0.0.0"]