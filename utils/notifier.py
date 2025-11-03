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
    import sys
    
    headers = {"Content-Type": "application/json"}
    
    # Handle authentication - check for token first, then auth dict
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif auth and auth.get("schemes") == ["Bearer"]:
        if "credentials" in auth:
            headers["Authorization"] = f"Bearer {auth['credentials']}"

    # Debug logging - use sys.stderr to ensure it's captured
    debug_msg = "=" * 80 + "\n"
    debug_msg += "WEBHOOK DEBUG INFO:\n"
    debug_msg += f"URL: {url}\n"
    debug_msg += f"Token present: {token is not None}\n"
    debug_msg += f"Token value (first 20 chars): {token[:20] if token else 'None'}...\n"
    debug_msg += f"Auth dict: {auth}\n"
    debug_msg += f"Headers keys: {list(headers.keys())}\n"
    debug_msg += "Payload preview (first 1000 chars):\n"
    payload_str = json.dumps(dict(payload), indent=2)
    debug_msg += payload_str[:1000] + "\n"
    debug_msg += "=" * 80 + "\n"
    
    sys.stderr.write(debug_msg)
    sys.stderr.flush()
    
    logging.info(f"Sending webhook to {url}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=dict(payload), headers=headers)
        
        error_msg = f"Webhook response status: {response.status_code}\n"
        if response.status_code >= 400:
            error_msg += f"Webhook error response body: {response.text}\n"
            error_msg += f"Response headers: {dict(response.headers)}\n"
        
        sys.stderr.write(error_msg)
        sys.stderr.flush()
        
        response.raise_for_status()
