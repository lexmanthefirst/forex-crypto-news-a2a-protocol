from __future__ import annotations

import logging
from typing import Any, Mapping

import httpx


async def send_console_notification(message: str) -> None:
    logging.info("Market Notification: %s", message)


async def send_webhook_notification(
    url: str,
    payload: Mapping[str, Any],
    token: str | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> None:
    """Send result to webhook URL"""
    import json
    
    headers = {"Content-Type": "application/json"}
    
    # Handle authentication - check for token first, then auth dict
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif auth and auth.get("schemes") == ["Bearer"]:
        if "credentials" in auth:
            headers["Authorization"] = f"Bearer {auth['credentials']}"

    # Debug logging
    print("=" * 80)
    print("WEBHOOK DEBUG INFO:")
    print(f"URL: {url}")
    print(f"Token present: {token is not None}")
    print(f"Auth dict: {auth}")
    print(f"Headers: {headers}")
    print("Payload preview (first 500 chars):")
    payload_str = json.dumps(dict(payload), indent=2)
    print(payload_str[:500])
    print("=" * 80)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=dict(payload), headers=headers)
        print(f"Webhook response status: {response.status_code}")
        if response.status_code >= 400:
            print(f"Webhook error response body: {response.text}")
        response.raise_for_status()
