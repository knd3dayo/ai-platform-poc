#!/bin/sh
set -eu

basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

# env_file="$basedir/env_run"
# . "$env_file"

usage() {
  cat >&2 <<'EOF'
Usage:
  ./run-opencode-web.sh [--config <dir>] [--host <host>] <command> [args...]

Commands:
  up        Start server (docker compose up -d)
  down      Stop and remove containers (docker compose down)
  stop      Stop container (docker compose stop)
  restart   Restart container (docker compose restart)
  logs      Show logs (docker compose logs)

Options:
  --config <dir>   Copy <dir> contents into workspace before running (default: ./config/common)
  --host <host>    Bind opencode web to <host> (default: 0.0.0.0)
  -h, --help       Show this help

Notes:
  - This script manages opencode web via docker compose.
EOF
}


compose_file="$basedir/docker-compose.yml"
service_name="denodo-ai-sdk"

if [ ! -f "$compose_file" ]; then
  echo "Compose file not found: $compose_file" >&2
  exit 1
fi

USER_ID=$(id -u)
GROUP_ID=$(id -g)


compose_env="USER_ID=$USER_ID GROUP_ID=$GROUP_ID"

subcommand="$1"

case "$subcommand" in
  up)
    env $compose_env docker compose -f "$compose_file" up -d "$service_name"
    ;;
  down)
    env $compose_env docker compose -f "$compose_file" down
    ;;
  stop)
    env $compose_env docker compose -f "$compose_file" stop "$service_name"
    ;;
  restart)
    env $compose_env docker compose -f "$compose_file" restart "$service_name"
    ;;
  logs)
    # Pass-through args to docker compose logs (e.g. -f, --tail)
    env $compose_env docker compose -f "$compose_file" logs "$service_name"
    ;;
  *)
    echo "Unknown command: $subcommand" >&2
    usage
    exit 1
    ;;
esac
