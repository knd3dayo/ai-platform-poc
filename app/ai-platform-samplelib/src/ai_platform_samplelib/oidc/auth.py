from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from typing import Any, cast

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai_platform_samplelib.oidc.oauth_client_auth import build_introspection_request_auth
from ai_platform_samplelib.oidc.settings import get_settings


current_access_token: ContextVar[str] = ContextVar("oidc_access_token", default="")
current_claims: ContextVar[dict[str, Any]] = ContextVar("oidc_claims", default={})

security = HTTPBearer(auto_error=False)


class JWKSCache:
    _jwks: dict[str, Any] | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_jwks(cls) -> dict[str, Any]:
        if cls._jwks is not None:
            return cls._jwks

        settings = get_settings()
        async with cls._lock:
            if cls._jwks is not None:
                return cls._jwks
            async with httpx.AsyncClient(timeout=settings.client.request_timeout_seconds) as client:
                response = await client.get(settings.zitadel.jwks_url)
                response.raise_for_status()
            cls._jwks = response.json()
            if cls._jwks is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to load JWKS",
                )
            return cls._jwks

    @classmethod
    def clear(cls) -> None:
        cls._jwks = None


def _select_signing_key(kid: str, jwks: dict[str, Any]) -> Any:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return RSAAlgorithm.from_jwk(json.dumps(key))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Signing key not found for token",
    )


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


def _claims_from_introspection(token: str, introspection: dict[str, Any]) -> dict[str, Any]:
    active = introspection.get("active")
    if not active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Opaque token introspection reported inactive token. "
                "In ZITADEL this usually means the introspection client is not part of the token audience."
            ),
        )

    claims = dict(introspection)
    claims.setdefault("sub", introspection.get("sub") or introspection.get("username"))
    claims.setdefault("scope", introspection.get("scope"))
    claims.setdefault("token_type", introspection.get("token_type", "Bearer"))
    claims.setdefault("raw_access_token", token)
    return claims


async def verify_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not _looks_like_jwt(token):
        introspection = await introspect_token(token)
        return _claims_from_introspection(token, introspection)

    try:
        header = jwt.get_unverified_header(token)
        jwks = await JWKSCache.get_jwks()
        signing_key = _select_signing_key(header["kid"], jwks)
        audience = settings.expected_audience
        options = cast(Any, {"verify_aud": audience is not None})
        return jwt.decode(
            token,
            key=signing_key,
            algorithms=[header.get("alg", "RS256")],
            audience=audience,
            issuer=settings.zitadel.issuer,
            options=options,
            leeway=settings.server.clock_skew_seconds,
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
        ) from exc


async def fetch_userinfo(token: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.client.request_timeout_seconds) as client:
        response = await client.get(
            settings.zitadel.userinfo_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


async def introspect_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        auth_fields, auth = build_introspection_request_auth(settings)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    async with httpx.AsyncClient(timeout=settings.client.request_timeout_seconds) as client:
        form_data = {"token": token, "token_type_hint": "access_token"}
        form_data.update(auth_fields)
        request_kwargs: dict[str, Any] = {
            "data": form_data,
        }
        if auth is not None:
            request_kwargs["auth"] = auth
        response = await client.post(settings.zitadel.introspection_url, **request_kwargs)
        response.raise_for_status()
        return response.json()


async def get_current_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )

    claims = await verify_access_token(credentials.credentials)
    current_access_token.set(credentials.credentials)
    current_claims.set(claims)
    return claims


def _normalize_scope_values(raw_scope: Any) -> set[str]:
    if raw_scope is None:
        return set()
    if isinstance(raw_scope, str):
        return {item for item in raw_scope.split() if item}
    if isinstance(raw_scope, list):
        return {str(item) for item in raw_scope if item}
    return set()


def _normalize_claim_values(raw_value: Any) -> set[str]:
    if raw_value is None:
        return set()
    if isinstance(raw_value, str):
        return {item for item in raw_value.split() if item}
    if isinstance(raw_value, list):
        return {str(item) for item in raw_value if item is not None}
    if isinstance(raw_value, dict):
        normalized: set[str] = set()
        for key, value in raw_value.items():
            if value in (True, None):
                normalized.add(str(key))
                continue
            if isinstance(value, dict):
                normalized.add(str(key))
                continue
            normalized.add(str(value))
        return normalized
    return {str(raw_value)}


def require_scopes(required_scopes: list[str]):
    async def dependency(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        granted_scopes = _normalize_scope_values(claims.get("scope") or claims.get("scp"))
        missing = [scope for scope in required_scopes if scope not in granted_scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(missing)}",
            )
        return claims

    return dependency


def require_client_ids(allowed_client_ids: list[str]):
    async def dependency(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        client_id = claims.get("client_id") or claims.get("azp")
        if client_id not in allowed_client_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client is not allowed to access this resource",
            )
        return claims

    return dependency


def require_claim_values(required_claim_values: dict[str, list[str]]):
    async def dependency(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        missing: dict[str, list[str]] = {}
        for claim_name, required_values in required_claim_values.items():
            granted_values = _normalize_claim_values(claims.get(claim_name))
            if not granted_values.issuperset(required_values):
                missing[claim_name] = required_values

        if missing:
            formatted = ", ".join(
                f"{claim_name}={ '|'.join(values) }" for claim_name, values in missing.items()
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required claim values: {formatted}",
            )

        return claims

    return dependency


def require_project_roles(required_roles: list[str], claim_keys: list[str]):
    async def dependency(claims: dict[str, Any] = Depends(get_current_claims)) -> dict[str, Any]:
        granted_roles: set[str] = set()
        for claim_key in claim_keys:
            granted_roles.update(_normalize_claim_values(claims.get(claim_key)))

        missing_roles = [role for role in required_roles if role not in granted_roles]
        if missing_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required project roles: {', '.join(missing_roles)}",
            )

        return claims

    return dependency