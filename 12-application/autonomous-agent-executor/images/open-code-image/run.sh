#!/bin/sh
service_name=${COMPOSE_SERVICE_NAME:-open-code-executor}
command="opencode"

# USER_IDとGROUP_IDを実行ユーザーから取得して、codeuserのUIDとGIDを変更する処理を追加
USER_ID=$(id -u)
GROUP_ID=$(id -g)

env WORKSPACE=${WORKSPACE:-./workspace} USER_ID=$USER_ID GROUP_ID=$GROUP_ID docker compose run --rm $service_name $command $@
