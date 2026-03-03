#!/bin/sh
set -eu

basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

env_file="$basedir/.env"
if [ ! -f "$env_file" ]; then
	env_file="$basedir/.env_template"
fi

. "$env_file"

cleanup() {
	rm -rf "$basedir/ai-platform-samplelib"
}
trap cleanup EXIT

: "${AI_PLATFORM_LIB:?AI_PLATFORM_LIB is required (path to ai-platform-samplelib)}"
cp -pr "$AI_PLATFORM_LIB" "$basedir/ai-platform-samplelib"

docker build \
	-t my-executor:latest \
	-f "$basedir/Dockerfile" \
	--build-arg AI_PLATFORM_LIB=ai-platform-samplelib \
	.
