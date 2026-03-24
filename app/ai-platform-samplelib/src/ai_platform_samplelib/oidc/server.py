from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

import httpx
import uvicorn
from fastapi import Depends, FastAPI

from ai_platform_samplelib.oidc.auth import (
    current_access_token,
    fetch_userinfo,
    get_current_claims,
    introspect_token,
    require_client_ids,
    require_scopes,
)
from ai_platform_samplelib.oidc.settings import OIDCSettings, get_settings


def create_app(settings: OIDCSettings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="Zitadel OIDC Test Server", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    async def config() -> dict[str, Any]:
        return {
            "issuer": active_settings.zitadel.issuer,
            "jwks_url": active_settings.zitadel.jwks_url,
            "userinfo_url": active_settings.zitadel.userinfo_url,
            "introspection_url": active_settings.zitadel.introspection_url,
            "expected_audience": active_settings.expected_audience,
            "resolved_scopes": active_settings.resolved_scopes,
            "downstream": {
                "backend_base_url": active_settings.downstream.backend_base_url,
                "backend_path": active_settings.downstream.backend_path,
            },
            "authorization": {
                "allowed_client_ids": active_settings.authorization.allowed_client_ids,
                "required_scopes": active_settings.authorization.required_scopes,
            },
        }

    @app.get("/protected/me")
    async def protected_me(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        return {
            "authenticated": True,
            "subject": claims.get("sub"),
            "issuer": claims.get("iss"),
            "audience": claims.get("aud"),
            "scope": claims.get("scope"),
            "claims": claims,
        }

    @app.get("/protected/ping")
    async def protected_ping(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        return {
            "message": "OIDC token verified successfully",
            "subject": claims.get("sub"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/protected/userinfo")
    async def protected_userinfo(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        userinfo = await fetch_userinfo(current_access_token.get())
        return {
            "verified_claims": claims,
            "userinfo": userinfo,
        }

    @app.get("/protected/introspect")
    async def protected_introspect(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        introspection = await introspect_token(current_access_token.get())
        return {
            "verified_claims": claims,
            "introspection": introspection,
        }

    @app.get("/protected/authorize/client")
    async def protected_authorize_client(
        claims: dict[str, Any] = Depends(
            require_client_ids(active_settings.authorization.allowed_client_ids)
        ),
    ) -> dict[str, Any]:
        return {
            "authorized": True,
            "authorization_type": "client_id",
            "client_id": claims.get("client_id") or claims.get("azp"),
            "allowed_client_ids": active_settings.authorization.allowed_client_ids,
        }

    @app.get("/protected/authorize/scope")
    async def protected_authorize_scope(
        claims: dict[str, Any] = Depends(require_scopes(active_settings.authorization.required_scopes)),
    ) -> dict[str, Any]:
        return {
            "authorized": True,
            "authorization_type": "scope",
            "required_scopes": active_settings.authorization.required_scopes,
            "granted_scope": claims.get("scope") or claims.get("scp"),
        }

    @app.get("/protected/forward/backend")
    async def protected_forward_backend(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        backend_url = (
            f"{active_settings.downstream.backend_base_url.rstrip('/')}"
            f"/{active_settings.downstream.backend_path.lstrip('/')}"
        )
        async with httpx.AsyncClient(timeout=active_settings.client.request_timeout_seconds) as client:
            response = await client.get(
                backend_url,
                headers={"Authorization": f"Bearer {current_access_token.get()}"},
            )
            response.raise_for_status()
            backend_response = response.json()

        return {
            "forwarded": True,
            "backend_url": backend_url,
            "caller_subject": claims.get("sub"),
            "backend_response": backend_response,
        }

    return app


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Zitadel OIDC test server")
    parser.add_argument("--host", default=settings.server.host, help="Host to bind")
    parser.add_argument("--port", type=int, default=settings.server.port, help="Port to bind")
    args = parser.parse_args()
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()