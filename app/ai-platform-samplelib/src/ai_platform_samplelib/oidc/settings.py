from __future__ import annotations

import base64
import os
from functools import lru_cache
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yml"
DEFAULT_ENV_PATH = BASE_DIR / ".env"

load_dotenv(DEFAULT_ENV_PATH)


class ZitadelSettings(BaseModel):
    base_url: str
    token_path: str = "/oauth/v2/token"
    jwks_path: str = "/oauth/v2/keys"
    userinfo_path: str = "/oidc/v1/userinfo"
    introspection_path: str = "/oauth/v2/introspect"
    expected_issuer: str | None = None
    expected_audiences: list[str] = Field(default_factory=list)
    default_scopes: list[str] = Field(default_factory=lambda: ["openid", "profile"])

    @property
    def token_url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.token_path}"

    @property
    def jwks_url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.jwks_path}"

    @property
    def userinfo_url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.userinfo_path}"

    @property
    def introspection_url(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.introspection_path}"

    @property
    def issuer(self) -> str:
        return self.expected_issuer or self.base_url.rstrip("/")


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 5801
    clock_skew_seconds: int = 30


class DownstreamSettings(BaseModel):
    backend_base_url: str = "http://localhost:5801"
    backend_path: str = "/backend/whoami"


class AuthorizationSettings(BaseModel):
    allowed_client_ids: list[str] = Field(default_factory=lambda: ["login-client"])
    required_scopes: list[str] = Field(default_factory=list)
    required_project_roles: list[str] = Field(default_factory=list)
    project_role_claim_keys: list[str] = Field(
        default_factory=lambda: [
            "urn:zitadel:iam:org:project:roles",
            "urn:zitadel:iam:org:project:365171666990530564:roles",
        ]
    )
    required_claim_values: dict[str, list[str]] = Field(default_factory=dict)


class ClientSettings(BaseModel):
    server_base_url: str = "http://localhost:5801"
    request_timeout_seconds: float = 20.0
    verify_tls: bool = True
    requested_scopes: list[str] = Field(default_factory=lambda: ["openid", "profile"])


class OIDCSettings(BaseModel):
    zitadel: ZitadelSettings
    server: ServerSettings
    downstream: DownstreamSettings = Field(default_factory=DownstreamSettings)
    authorization: AuthorizationSettings = Field(default_factory=AuthorizationSettings)
    client: ClientSettings

    def _load_application_key_from_env(self) -> dict | None:
        raw_json = os.getenv("OIDC_TEST_APPLICATION_KEY_JSON")
        if raw_json:
            return json.loads(raw_json)

        raw_b64 = os.getenv("OIDC_TEST_APPLICATION_KEY_B64")
        if raw_b64:
            decoded = base64.b64decode(raw_b64).decode("utf-8")
            return json.loads(decoded)

        return None

    @property
    def expected_audience(self) -> str | list[str] | None:
        explicit_audience = os.getenv("OIDC_TEST_AUDIENCE")
        if explicit_audience:
            return explicit_audience

        explicit_audiences = os.getenv("OIDC_TEST_AUDIENCES")
        if explicit_audiences:
            parsed = [item.strip() for item in explicit_audiences.split(",") if item.strip()]
            if parsed:
                return parsed

        if self.zitadel.expected_audiences:
            return self.zitadel.expected_audiences

        client_id = os.getenv("ZITADEL_CLIENT_ID")
        return client_id or None

    @property
    def client_id(self) -> str | None:
        return os.getenv("ZITADEL_CLIENT_ID")

    @property
    def client_secret(self) -> str | None:
        return os.getenv("ZITADEL_CLIENT_SECRET")

    @property
    def application_key_path(self) -> Path | None:
        configured = os.getenv("OIDC_TEST_APPLICATION_KEY_PATH")
        if not configured:
            return None
        return Path(configured)

    @property
    def introspection_application_key_path(self) -> Path | None:
        configured = os.getenv("OIDC_TEST_INTROSPECTION_APPLICATION_KEY_PATH")
        if not configured:
            return None
        return Path(configured)

    @property
    def application_key(self) -> dict | None:
        env_key = self._load_application_key_from_env()
        if env_key is not None:
            return env_key

        key_path = self.application_key_path
        if key_path is None:
            return None
        return json.loads(key_path.read_text(encoding="utf-8"))

    @property
    def introspection_application_key(self) -> dict | None:
        key_path = self.introspection_application_key_path
        if key_path is not None:
            return json.loads(key_path.read_text(encoding="utf-8"))

        if self.application_key_kind == "application":
            return self.application_key

        return None

    @property
    def preferred_client_auth_method(self) -> str:
        key_kind = self.application_key_kind
        if key_kind == "service_account":
            return "service_account_jwt_bearer"
        if key_kind == "application":
            return "private_key_jwt"
        return "client_secret_basic"

    @property
    def application_key_kind(self) -> str | None:
        application_key = self.application_key
        if application_key is None:
            return None

        if application_key.get("type") == "serviceaccount" or application_key.get("userId"):
            return "service_account"

        if application_key.get("clientId"):
            return "application"

        return None

    @property
    def resolved_scopes(self) -> list[str]:
        explicit_scopes = os.getenv("OIDC_TEST_SCOPES")
        if explicit_scopes is not None:
            return [item.strip() for item in explicit_scopes.split(",") if item.strip()]

        if self.client.requested_scopes:
            return self.client.requested_scopes

        return self.zitadel.default_scopes


def _resolve_config_path() -> Path:
    configured_path = os.getenv("OIDC_TEST_CONFIG")
    if configured_path:
        return Path(configured_path)
    return DEFAULT_CONFIG_PATH


@lru_cache(maxsize=1)
def get_settings() -> OIDCSettings:
    config_path = _resolve_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}
    return OIDCSettings.model_validate(raw_config)