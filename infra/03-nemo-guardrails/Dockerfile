FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel \
    && pip install "nemoguardrails[server,openai]"

WORKDIR /app

RUN mkdir -p /config

EXPOSE 8000

CMD ["nemoguardrails", "server", "--config=/config", "--port=8000"]
