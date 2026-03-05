#!/bin/sh
set -eu
basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

env_file="$basedir/.env"
. "$env_file"

if [ $# -eq 0 ]; then
  # commandはopen-code、claude、clineのいずれかを想定しているが、指定されない場合はエラーとする
  echo "Usage: $0 <command: open-code|claude|cline> [args...]" >&2
  exit 1
elif [ "$1" != "open-code" ] && [ "$1" != "claude" ] && [ "$1" != "cline" ]; then
  echo "Invalid command: $1" >&2
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

env WORKSPACE=${WORKSPACE:-./workspace} USER_ID=$USER_ID GROUP_ID=$GROUP_ID docker compose run --rm $service_name $command $@
