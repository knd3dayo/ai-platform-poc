from __future__ import annotations

import argparse
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI

from ai_platform_samplelib.oidc.auth import (
    get_current_claims,
    require_claim_values,
    require_client_ids,
    require_project_roles,
    require_scopes,
)
from ai_platform_samplelib.oidc.settings import OIDCSettings, get_settings


def create_app(settings: OIDCSettings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(title="Zitadel OIDC Backend Server", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/config")
    async def config() -> dict[str, Any]:
        return {
            "issuer": active_settings.zitadel.issuer,
            "expected_audience": active_settings.expected_audience,
            "authorization": {
                "allowed_client_ids": active_settings.authorization.allowed_client_ids,
                "required_scopes": active_settings.authorization.required_scopes,
                "required_project_roles": active_settings.authorization.required_project_roles,
                "project_role_claim_keys": active_settings.authorization.project_role_claim_keys,
                "required_claim_values": active_settings.authorization.required_claim_values,
            },
        }

    @app.get("/backend/whoami")
    async def backend_whoami(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        return {
            "backend_authenticated": True,
            "subject": claims.get("sub"),
            "client_id": claims.get("client_id") or claims.get("azp"),
            "audience": claims.get("aud"),
            "claims": claims,
        }

    @app.get("/backend/authorize/client")
    async def backend_authorize_client(
        claims: dict[str, Any] = Depends(
            require_client_ids(active_settings.authorization.allowed_client_ids)
        ),
    ) -> dict[str, Any]:
        return {
            "authorized": True,
            "authorization_type": "client_id",
            "client_id": claims.get("client_id") or claims.get("azp"),
        }

    @app.get("/backend/authorize/scope")
    async def backend_authorize_scope(
        claims: dict[str, Any] = Depends(require_scopes(active_settings.authorization.required_scopes)),
    ) -> dict[str, Any]:
        return {
            "authorized": True,
            "authorization_type": "scope",
            "required_scopes": active_settings.authorization.required_scopes,
            "granted_scope": claims.get("scope") or claims.get("scp"),
        }

    @app.get("/backend/authorize/role")
    async def backend_authorize_role(
        claims: dict[str, Any] = Depends(
            require_project_roles(
                active_settings.authorization.required_project_roles,
                active_settings.authorization.project_role_claim_keys,
            )
        ),
    ) -> dict[str, Any]:
        return {
            "authorized": True,
            "authorization_type": "project_role",
            "required_project_roles": active_settings.authorization.required_project_roles,
            "project_role_claim_keys": active_settings.authorization.project_role_claim_keys,
        }

    @app.get("/backend/authorize/claims")
    async def backend_authorize_claims(
        claims: dict[str, Any] = Depends(
            require_claim_values(active_settings.authorization.required_claim_values)
        ),
    ) -> dict[str, Any]:
        return {
            "authorized": True,
            "authorization_type": "custom_claims",
            "required_claim_values": active_settings.authorization.required_claim_values,
            "claims": claims,
        }

    return app


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Zitadel OIDC backend server")
    parser.add_argument("--host", default=settings.server.host, help="Host to bind")
    parser.add_argument("--port", type=int, default=5802, help="Port to bind")
    args = parser.parse_args()
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()