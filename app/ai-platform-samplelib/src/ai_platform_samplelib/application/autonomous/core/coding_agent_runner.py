"""Backward-compatible module alias.

Historically, callers imported `CodingAgentRunner` from this module.
The implementation was renamed to `docker_coding_agent_runner` to clarify the
backend. Keep this shim to avoid breaking existing imports.
"""

from __future__ import annotations

from .docker_coding_agent_runner import CodingAgentRunner

__all__ = ["CodingAgentRunner"]
