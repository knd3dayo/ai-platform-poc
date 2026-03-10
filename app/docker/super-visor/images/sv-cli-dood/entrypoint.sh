#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="${WORKSPACE_ROOT:-/srv/ai_platform/workspaces}"

mkdir -p "$WORKSPACE_ROOT"

# If the workspace root is bind-mounted from host, it may be owned by root.
# For PoC convenience, allow mapping ownership to the host user.
if [[ -n "${HOST_UID:-}" && -n "${HOST_GID:-}" ]]; then
  chown -R "${HOST_UID}:${HOST_GID}" "$WORKSPACE_ROOT" 2>/dev/null || true
fi

# Propagate host uid/gid to executor runner (CodingAgentRunner reads AI_PLATFORM_HOST_UID/GID)
if [[ -n "${HOST_UID:-}" ]]; then export AI_PLATFORM_HOST_UID="$HOST_UID"; fi
if [[ -n "${HOST_GID:-}" ]]; then export AI_PLATFORM_HOST_GID="$HOST_GID"; fi

exec python -m ai_platform_samplelib.application.super_visor.cli.main "$@"
