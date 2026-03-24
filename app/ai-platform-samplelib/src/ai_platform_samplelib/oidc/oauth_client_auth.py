from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from ai_platform_samplelib.oidc.settings import OIDCSettings


CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
JWT_BEARER_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def resolve_client_id(settings: OIDCSettings) -> str:
    application_key = settings.application_key
    if application_key is not None and application_key.get("clientId"):
        return application_key["clientId"]

    client_id = settings.client_id
    if not client_id:
        raise RuntimeError("ZITADEL_CLIENT_ID must be set")
    return client_id


def _resolve_application_client_id(application_key: dict) -> str:
    client_id = application_key.get("clientId")
    if not client_id:
        raise RuntimeError("Application key JSON must contain clientId")
    return client_id


def _build_signed_jwt(subject: str, key_id: str, private_key: str, audience: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": subject,
        "sub": subject,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": str(uuid4()),
    }
    headers = {
        "alg": "RS256",
        "kid": key_id,
        "typ": "JWT",
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers=headers)


def build_private_key_client_assertion(settings: OIDCSettings) -> str:
    application_key = settings.application_key
    if application_key is None:
        raise RuntimeError(
            "Set OIDC_TEST_APPLICATION_KEY_PATH, OIDC_TEST_APPLICATION_KEY_JSON, or OIDC_TEST_APPLICATION_KEY_B64"
        )

    client_id = _resolve_application_client_id(application_key)
    return _build_signed_jwt(client_id, application_key["keyId"], application_key["key"], settings.zitadel.issuer)


def build_service_account_assertion(settings: OIDCSettings) -> str:
    application_key = settings.application_key
    if application_key is None or not application_key.get("userId"):
        raise RuntimeError("A service account key JSON with userId is required")

    user_id = application_key["userId"]
    return _build_signed_jwt(user_id, application_key["keyId"], application_key["key"], settings.zitadel.issuer)


def build_introspection_request_auth(settings: OIDCSettings) -> tuple[dict[str, str], tuple[str, str] | None]:
    application_key = settings.introspection_application_key
    if application_key is not None:
        client_id = _resolve_application_client_id(application_key)
        client_assertion = _build_signed_jwt(
            client_id,
            application_key["keyId"],
            application_key["key"],
            settings.zitadel.issuer,
        )
        return {
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": client_assertion,
        }, None

    client_id = settings.client_id
    client_secret = settings.client_secret
    if client_id and client_secret:
        return {}, (client_id, client_secret)

    raise RuntimeError(
        "Set OIDC_TEST_INTROSPECTION_APPLICATION_KEY_PATH or provide ZITADEL_CLIENT_ID/ZITADEL_CLIENT_SECRET"
    )


def build_token_request_auth(settings: OIDCSettings) -> tuple[dict[str, str], tuple[str, str] | None]:
    if settings.preferred_client_auth_method == "private_key_jwt":
        return {
            "client_id": resolve_client_id(settings),
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": build_private_key_client_assertion(settings),
        }, None

    if settings.preferred_client_auth_method == "service_account_jwt_bearer":
        return {}, None

    client_id = settings.client_id
    client_secret = settings.client_secret
    if not client_id or not client_secret:
        raise RuntimeError("ZITADEL_CLIENT_ID and ZITADEL_CLIENT_SECRET must be set in the environment")
    return {}, (client_id, client_secret)


def build_token_request(settings: OIDCSettings, requested_scope: str) -> tuple[dict[str, str], tuple[str, str] | None]:
    normalized_scope = requested_scope.strip()

    if settings.preferred_client_auth_method == "service_account_jwt_bearer":
        form_data = {
            "grant_type": JWT_BEARER_GRANT_TYPE,
            "assertion": build_service_account_assertion(settings),
        }
        form_data["scope"] = normalized_scope or "openid"
        return form_data, None

    form_data = {"grant_type": "client_credentials"}
    if normalized_scope:
        form_data["scope"] = normalized_scope
    auth_fields, auth = build_token_request_auth(settings)
    form_data.update(auth_fields)
    return form_data, auth