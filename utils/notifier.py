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
    timeout: float = 10.0,
) -> None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=dict(payload), headers=headers)
        response.raise_for_status()
