#!/bin/sh
set -eu
basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

env_file="$basedir/.env"
. "$env_file"

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
