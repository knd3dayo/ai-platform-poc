#!/bin/sh
set -eu
image_name="cline-executor-image"
basedir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$basedir"

env_file="$basedir/.env"
if [ ! -f "$env_file" ]; then
	env_file="$basedir/.env_template"
fi

. "$env_file"

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
