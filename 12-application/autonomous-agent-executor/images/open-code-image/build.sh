#!/bin/sh
set -eu

basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

env_file="$basedir/.env"
. "$env_file"

image_name="${IMAGE_NAME}"

if [ -z "$image_name" ]; then
	echo "IMAGE_NAME is not set in .env or .env_template" >&2
	exit 1
fi

cleanup() {
	rm -rf "$basedir/ai-platform-samplelib"
	rm -rf "$basedir/mcp"
}
trap cleanup EXIT

: "${AI_PLATFORM_LIB:?AI_PLATFORM_LIB is required (path to ai-platform-samplelib)}"
cp -pr "$AI_PLATFORM_LIB" "$basedir/ai-platform-samplelib"
: "${MCP_LIB:?MCP_LIB is required (path to mcp)}"
cp -pr "$MCP_LIB" "$basedir/mcp"

docker build \
	-t "$image_name" \
	-f "$basedir/Dockerfile" \
	.
