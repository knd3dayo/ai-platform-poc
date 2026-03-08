#!/bin/sh
set -eu

basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

usage() {
  cat >&2 <<'EOF'
Usage:
  ./run.sh [command ...]

Examples:
  ./run.sh id
  ./run.sh /bin/bash
  ./run.sh python -V

Notes:
  - Runs the service with host UID/GID via docker-compose user: setting.
  - env_compose is loaded by docker-compose.yml (env_file).
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

USER_ID="$(id -u)"
GROUP_ID="$(id -g)"

# If no command is provided, let the image default CMD/entrypoint handle it.
# (entrypoint.sh falls back to /bin/bash)

env USER_ID="$USER_ID" GROUP_ID="$GROUP_ID" docker compose run --rm denodo-ai-sdk "$@"
