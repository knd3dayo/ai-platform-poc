FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 【ここがポイント】仮想環境の作成場所をマウントされない場所（例: /opt/venv）に固定する
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# 1. 依存関係の定義ファイルだけを先にコピー
COPY pyproject.toml uv.lock ./

# 2. 【重要】プロジェクト自体をインストールせずに、ライブラリだけを先に同期
# これにより、srcフォルダがなくてもエラーになりません
RUN uv sync --frozen --no-dev --no-install-project

# 3. ここで初めてソースコード全体（srcフォルダ等）をコピー
COPY . .

# 4. 最後にプロジェクト自体を同期（ソースコードがあるので成功する）
# すでにライブラリはインストール済みなので、このステップは一瞬で終わります
RUN uv sync --frozen --no-dev