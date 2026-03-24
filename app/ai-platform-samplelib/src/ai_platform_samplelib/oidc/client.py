from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import httpx

from ai_platform_samplelib.oidc.oauth_client_auth import build_token_request
from ai_platform_samplelib.oidc.settings import get_settings


async def fetch_access_token(scope: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    requested_scope = scope if scope is not None else " ".join(settings.resolved_scopes)
    form_data, auth = build_token_request(settings, requested_scope)
    async with httpx.AsyncClient(timeout=settings.client.request_timeout_seconds) as client:
        response = await client.post(
            settings.zitadel.token_url,
            data=form_data,
            auth=auth,
        )
        response.raise_for_status()
        return response.json()


async def call_protected_api(path: str, token: str) -> httpx.Response:
    settings = get_settings()
    url = f"{settings.client.server_base_url.rstrip('/')}/{path.lstrip('/')}"
    async with httpx.AsyncClient(
        timeout=settings.client.request_timeout_seconds,
        verify=settings.client.verify_tls,
    ) as client:
        return await client.get(url, headers={"Authorization": f"Bearer {token}"})


async def main_async() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Zitadel OIDC test client")
    parser.add_argument(
        "--path",
        default="/protected/me",
        help="Server path to call after fetching a token",
    )
    parser.add_argument(
        "--scope",
        default=" ".join(settings.resolved_scopes),
        help="Space separated scopes for the token request",
    )
    parser.add_argument(
        "--print-token",
        action="store_true",
        help="Print token payload before calling the server",
    )
    args = parser.parse_args()

    token_response = await fetch_access_token(args.scope)
    access_token = token_response["access_token"]

    if args.print_token:
        print(json.dumps(token_response, indent=2, ensure_ascii=False))

    response = await call_protected_api(args.path, access_token)
    print(f"status_code={response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()