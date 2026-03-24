from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from ai_platform_samplelib.oidc.oauth_client_auth import build_token_request
from ai_platform_samplelib.oidc.settings import get_settings


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = BASE_DIR / ".env"
load_dotenv(DEFAULT_ENV_PATH)


async def fetch_access_token(scope: str | None = None) -> dict:
    settings = get_settings()
    token_url = settings.zitadel.token_url
    requested_scope = scope if scope is not None else os.getenv("ZITADEL_SCOPES", "")
    form_data, auth = build_token_request(settings, requested_scope)

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            token_url,
            data=form_data,
            auth=auth,
        )

    print(f"token_status={response.status_code}")
    try:
        payload = response.json()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text)

    response.raise_for_status()
    return response.json()


async def call_api(base_url: str, path: str, token: str) -> None:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    print(f"api_status={response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text)


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Minimal Zitadel OIDC client")
    parser.add_argument("--scope", default=os.getenv("ZITADEL_SCOPES", ""), help="Space separated scopes")
    parser.add_argument(
        "--server-base-url",
        default=os.getenv("OIDC_TEST_SERVER_BASE_URL", "http://localhost:5801"),
        help="Target server base URL",
    )
    parser.add_argument("--path", default="/protected/me", help="Path to call after token acquisition")
    parser.add_argument("--token-only", action="store_true", help="Only fetch a token")
    args = parser.parse_args()

    token_response = await fetch_access_token(args.scope)
    if args.token_only:
        return

    await call_api(args.server_base_url, args.path, token_response["access_token"])


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()