#!/bin/sh
set -eu
basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

env_file="$basedir/.env"
. "$env_file"

usage() {
  cat >&2 <<'EOF'
Usage:
  ./run.sh [--config <dir>] [--host <host>] <command: opencode|claude|cline> [args...]

Options:
  --config <dir>   Copy <dir> contents into workspace before running (default: ./config/common)
  --host <host>    Alias for: opencode web --hostname <host> (only applied when running opencode web)
  -h, --help       Show this help
EOF
}

config_dir="$basedir/config/common"
opencode_web_host=""

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --config)
      shift
      if [ $# -eq 0 ]; then
        echo "--config requires an argument" >&2
        usage
        exit 1
      fi
      config_dir="$1"
      shift
      ;;
    --config=*)
      config_dir="${1#--config=}"
      shift
      ;;
    --host)
      shift
      if [ $# -eq 0 ]; then
        echo "--host requires an argument" >&2
        usage
        exit 1
      fi
      opencode_web_host="$1"
      shift
      ;;
    --host=*)
      opencode_web_host="${1#--host=}"
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [ $# -eq 0 ]; then
  # commandはopencode、claude、clineのいずれかを想定しているが、指定されない場合はエラーとする
  usage
  exit 1
elif [ "$1" = "open-code" ]; then
  echo "Invalid command: open-code (use: opencode)" >&2
  usage
  exit 1
elif [ "$1" != "opencode" ] && [ "$1" != "claude" ] && [ "$1" != "cline" ]; then
  echo "Invalid command: $1" >&2
  usage
  exit 1
else
  COMPOSE_COMMAND=$1
  shift
fi

service_name=${COMPOSE_SERVICE_NAME}
if [ -z "$service_name" ]; then
  echo "COMPOSE_SERVICE_NAME is not set in .env or .env_template" >&2
  exit 1
fi

command=${COMPOSE_COMMAND}

if [ -z "$command" ]; then
  echo "COMPOSE_COMMAND is not set in .env or .env_template" >&2
  exit 1
fi

# USER_IDとGROUP_IDを実行ユーザーから取得して、codeuserのUIDとGIDを変更する処理を追加
USER_ID=$(id -u)
GROUP_ID=$(id -g)

workspace_dir="${WORKSPACE:-./workspace}"

if [ ! -d "$config_dir" ]; then
  echo "Config directory not found: $config_dir" >&2
  exit 1
fi
mkdir -p "$workspace_dir"
# Copy config directory contents into workspace (include dotfiles).
cp -pr "$config_dir"/. "$workspace_dir"/

compose_run_extra_args=""
# docker compose run does not publish ports unless --service-ports is set.
if [ "$command" = "opencode" ] && [ "${1:-}" = "web" ]; then
  compose_run_extra_args="--service-ports"

  if [ -n "$opencode_web_host" ]; then
    has_hostname=0
    for arg in "$@"; do
      case "$arg" in
        --hostname|--hostname=*)
          has_hostname=1
          break
          ;;
      esac
    done

    if [ "$has_hostname" -eq 0 ]; then
      set -- "$@" --hostname "$opencode_web_host"
    fi
  fi
fi

env WORKSPACE=${WORKSPACE:-./workspace} USER_ID=$USER_ID GROUP_ID=$GROUP_ID docker compose run $compose_run_extra_args --rm $service_name $command $@
