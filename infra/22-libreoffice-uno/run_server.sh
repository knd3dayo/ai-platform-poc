#!/bin/sh
set -eu

python3 -m unoserver.server "$@" &
UNOSERVER_PID=$!

cleanup() {
  kill "$UNOSERVER_PID" 2>/dev/null || true
  wait "$UNOSERVER_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

exec python3 -m uvicorn uno_api_server.app:app \
  --host "${UNO_API_HOST:-0.0.0.0}" \
  --port "${UNO_API_PORT:-2004}"