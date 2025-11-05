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
    headers = {"Content-Type": "application/json"}
    
    # Handle authentication
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif auth and auth.get("schemes") == ["Bearer"]:
        if "credentials" in auth:
            headers["Authorization"] = f"Bearer {auth['credentials']}"

    # Convert payload to proper dict for JSON serialization
    payload_dict = dict(payload) if not isinstance(payload, dict) else payload
    
    logging.info(f"Sending webhook to {url}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload_dict, headers=headers)
        response.raise_for_status()
