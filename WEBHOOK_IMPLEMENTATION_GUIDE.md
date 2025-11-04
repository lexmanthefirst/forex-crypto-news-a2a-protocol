# Webhook Implementation Guide for A2A Agent

## Overview

This guide explains how to implement webhook-based (non-blocking) responses for your A2A agent and when you should use this pattern versus the current synchronous approach.

## Table of Contents

1. [When to Use Webhooks](#when-to-use-webhooks)
2. [How Webhooks Work](#how-webhooks-work)
3. [Implementation Steps](#implementation-steps)
4. [Complete Code Example](#complete-code-example)
5. [Testing](#testing)
6. [Troubleshooting](#troubleshooting)

---

## When to Use Webhooks

### ✅ Use Webhooks (Non-Blocking Mode) When:

- **Long-running processing**: Your agent needs >30 seconds to process requests (risk of HTTP timeout)
- **Complex workflows**: Multiple API calls, heavy data processing, or ML model inference
- **External dependencies**: Waiting on slow third-party services
- **Batch operations**: Processing multiple items that take time
- **User experience**: You want to show "Agent is thinking..." immediately while processing in background

### ❌ Don't Use Webhooks When:

- **Fast responses**: Processing completes in <10 seconds (current market analysis ~5-15s)
- **Simple queries**: Straightforward data retrieval or basic calculations
- **Client doesn't support webhooks**: Some A2A platforms may not implement webhook handling properly
- **Debugging**: Synchronous responses are easier to debug and test

---

## How Webhooks Work

### Synchronous Flow (Current Implementation)

```
Client → [Your Agent] → Process → Return Result → Client
         ←────────────────────────────────────────
                    Single HTTP Request
```

### Webhook Flow (Non-Blocking)

```
Client → [Your Agent] → Return ACK (result: null) → Client
         ↓
         Process in Background
         ↓
         POST result to webhook URL → Client receives via webhook
```

**Key Steps:**

1. **Immediate ACK**: Return `{"result": null}` immediately (tells client "working on it")
2. **Background Processing**: Process the request asynchronously
3. **Webhook Callback**: POST the actual result to the webhook URL provided by client
4. **Client Updates UI**: Client receives webhook and displays the result

---

## Implementation Steps

### Step 1: Update Models (If Needed)

Your models already support `pushNotificationConfig`. Verify it's present:

```python
# models/a2a.py
class PushNotificationConfig(BaseModel):
    url: str
    token: str | None = None
    authentication: dict[str, Any] | None = None

class MessageConfiguration(BaseModel):
    blocking: bool = True  # false = webhook mode
    pushNotificationConfig: PushNotificationConfig | None = None
    # ... other fields
```

### Step 2: Add Webhook Handler Function

```python
# main.py

async def _handle_nonblocking_request(
    request_id: str,
    messages: list[A2AMessage],
    config: MessageConfiguration
) -> JSONResponse:
    """Handle non-blocking request - return immediate ACK and process in background."""

    # 1. Return immediate acknowledgment with null result
    ack_response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=None)

    # 2. Start background processing (don't await)
    if config.pushNotificationConfig:
        asyncio.create_task(
            _process_and_send_webhook(
                messages=messages,
                config=config,
                request_id=request_id,
                webhook_url=config.pushNotificationConfig.url,
                webhook_token=config.pushNotificationConfig.token,
                webhook_auth=config.pushNotificationConfig.authentication
            )
        )

    return JSONResponse(content=ack_response.model_dump())
```

### Step 3: Add Background Processing Function

```python
# main.py

async def _process_and_send_webhook(
    messages: list[A2AMessage],
    config: MessageConfiguration,
    request_id: str,
    webhook_url: str,
    webhook_token: str | None = None,
    webhook_auth: dict[str, Any] | None = None,
) -> None:
    """Process request in background and send result via webhook."""
    import httpx

    try:
        # 1. Process the request (this can take time)
        result = await _process_with_agent(messages, config=config)

        # 2. Wrap in JSON-RPC response
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=request_id,
            result=result
        )

        # 3. Prepare webhook payload
        payload = response.model_dump(mode='json')

        # 4. Send to webhook URL
        await send_webhook_notification(
            url=webhook_url,
            payload=payload,
            token=webhook_token,
            auth=webhook_auth
        )

        print(f"✅ Successfully sent webhook to {webhook_url}")

    except Exception as exc:
        print(f"❌ Failed to process and send webhook: {exc}")
        traceback.print_exc()

        # Send error response to webhook
        try:
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"details": str(exc)}
                }
            }

            await send_webhook_notification(
                url=webhook_url,
                payload=error_response,
                token=webhook_token,
                auth=webhook_auth
            )
        except Exception as webhook_error:
            print(f"❌ Failed to send error webhook: {webhook_error}")
```

### Step 4: Update Request Handler to Support Both Modes

```python
# main.py

async def _handle_message_send(request_id: str, params: MessageParams) -> JSONResponse:
    """Handle message/send JSON-RPC method."""
    messages = [params.message]
    config = params.configuration

    # Check if non-blocking mode with webhook config
    if not config.blocking and config.pushNotificationConfig:
        # Non-blocking: return immediate ACK + process in background
        return await _handle_nonblocking_request(request_id, messages, config)
    else:
        # Blocking: process and return result immediately
        return await _handle_blocking_request(request_id, messages, config)
```

### Step 5: Ensure Webhook Notification Utility Exists

```python
# utils/notifier.py

import httpx
from typing import Any

async def send_webhook_notification(
    url: str,
    payload: dict[str, Any],
    token: str | None = None,
    auth: dict[str, Any] | None = None,
    timeout: int = 30
) -> None:
    """Send notification to webhook URL.

    Args:
        url: Webhook URL to POST to
        payload: JSON payload to send
        token: Optional Bearer token for authentication
        auth: Optional authentication config (e.g., {'schemes': ['Bearer']})
        timeout: Request timeout in seconds
    """
    headers = {"Content-Type": "application/json"}

    # Add authentication if provided
    if token:
        if auth and "Bearer" in auth.get("schemes", []):
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            print(f"✅ Webhook sent successfully: {response.status_code}")

        except httpx.HTTPStatusError as exc:
            print(f"❌ Webhook failed: {exc.response.status_code}")
            print(f"Response body: {exc.response.text}")
            raise
        except Exception as exc:
            print(f"❌ Webhook error: {exc}")
            raise
```

---

## Complete Code Example

Here's a complete `main.py` with webhook support:

```python
"""
A2A Market Intelligence Agent - With Webhook Support
"""
from __future__ import annotations

import asyncio
import os
import traceback
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from agents.market_agent import MarketAgent
from models.a2a import (
    A2AMessage,
    ExecuteParams,
    JSONRPCRequest,
    JSONRPCResponse,
    MessageConfiguration,
    MessageParams,
    TaskResult,
)
from utils.notifier import send_webhook_notification
from utils.redis_client import redis_store

app = FastAPI(title="Market Intelligence A2A", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

market_agent: MarketAgent | None = None

@asynccontextmanager
async def lifespan(_: FastAPI):
    global market_agent
    await redis_store.initialize()
    market_agent = MarketAgent()
    yield
    await redis_store.close()
    market_agent = None

app.router.lifespan_context = lifespan

# ===========================
# Request Parsing & Validation
# ===========================

async def _parse_request_body(request: Request) -> dict[str, Any] | JSONResponse:
    """Parse JSON body from request."""
    try:
        return await request.json()
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }
        )

async def _validate_jsonrpc_request(body: dict[str, Any]) -> JSONRPCRequest | JSONResponse:
    """Validate JSON-RPC request structure."""
    try:
        return JSONRPCRequest(**body)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {"code": -32600, "message": "Invalid Request"}
            }
        )

# ===========================
# Request Handlers
# ===========================

async def _handle_message_send(request_id: str, params: MessageParams) -> JSONResponse:
    """Handle message/send JSON-RPC method - supports both blocking and non-blocking modes."""
    messages = [params.message]
    config = params.configuration

    # Check if non-blocking mode with webhook
    if not config.blocking and config.pushNotificationConfig:
        return await _handle_nonblocking_request(request_id, messages, config)
    else:
        return await _handle_blocking_request(request_id, messages, config)

async def _handle_execute(request_id: str, params: ExecuteParams) -> JSONResponse:
    """Handle execute JSON-RPC method - always blocking."""
    result = await _process_with_agent(
        params.messages,
        context_id=params.contextId,
        task_id=params.taskId,
    )
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    return JSONResponse(content=response.model_dump())

async def _handle_blocking_request(
    request_id: str,
    messages: list[A2AMessage],
    config: MessageConfiguration
) -> JSONResponse:
    """Handle blocking request - return result directly."""
    result = await _process_with_agent(messages, config=config)
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    return JSONResponse(content=response.model_dump())

async def _handle_nonblocking_request(
    request_id: str,
    messages: list[A2AMessage],
    config: MessageConfiguration
) -> JSONResponse:
    """Handle non-blocking request - send immediate ACK and process in background."""

    # Return immediate acknowledgment
    ack_response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=None)

    # Start background processing
    if config.pushNotificationConfig:
        asyncio.create_task(
            _process_and_send_webhook(
                messages=messages,
                config=config,
                request_id=request_id,
                webhook_url=config.pushNotificationConfig.url,
                webhook_token=config.pushNotificationConfig.token,
                webhook_auth=config.pushNotificationConfig.authentication
            )
        )

    return JSONResponse(content=ack_response.model_dump())

# ===========================
# Main Endpoint
# ===========================

@app.post("/a2a/agent/market")
async def a2a_endpoint(request: Request):
    """Main A2A protocol endpoint - supports both blocking and non-blocking modes."""

    # Parse and validate
    body = await _parse_request_body(request)
    if isinstance(body, JSONResponse):
        return body

    rpc = await _validate_jsonrpc_request(body)
    if isinstance(rpc, JSONResponse):
        return rpc

    # Route to handler
    try:
        if isinstance(rpc.params, MessageParams):
            return await _handle_message_send(rpc.id, rpc.params)
        elif isinstance(rpc.params, ExecuteParams):
            return await _handle_execute(rpc.id, rpc.params)
        else:
            raise ValueError("Unsupported params payload")
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": rpc.id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"details": str(exc)}
                }
            }
        )

# ===========================
# Agent Processing
# ===========================

async def _process_with_agent(
    messages: list[A2AMessage],
    *,
    context_id: str | None = None,
    task_id: str | None = None,
    config: Any | None = None,
) -> TaskResult:
    """Process messages with the market agent."""
    if market_agent is None:
        raise RuntimeError("MarketAgent is not initialized")

    return await market_agent.process_messages(
        messages,
        context_id=context_id or "default",
        task_id=task_id or "default-task",
    )

async def _process_and_send_webhook(
    messages: list[A2AMessage],
    config: MessageConfiguration,
    request_id: str,
    webhook_url: str,
    webhook_token: str | None = None,
    webhook_auth: dict[str, Any] | None = None,
) -> None:
    """Process request in background and send result via webhook."""
    try:
        # Process the request
        result = await _process_with_agent(messages, config=config)

        # Wrap in JSON-RPC response
        response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)

        # Send to webhook
        await send_webhook_notification(
            url=webhook_url,
            payload=response.model_dump(mode='json'),
            token=webhook_token,
            auth=webhook_auth
        )

        print(f"✅ Webhook sent successfully to {webhook_url}")

    except Exception as exc:
        print(f"❌ Failed to process and send webhook: {exc}")
        traceback.print_exc()

        # Send error to webhook
        try:
            error_response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"details": str(exc)}
                }
            }

            await send_webhook_notification(
                url=webhook_url,
                payload=error_response,
                token=webhook_token,
                auth=webhook_auth
            )
        except Exception:
            print("❌ Failed to send error webhook")
            traceback.print_exc()

# ===========================
# Health Check
# ===========================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "mode": "blocking + non-blocking (webhook) support"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
```

---

## Testing

### Test 1: Blocking Mode (Current Behavior)

```bash
curl -X POST http://localhost:8000/a2a/agent/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-blocking-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "analyze BTC"}]
      },
      "configuration": {
        "blocking": true
      }
    }
  }'
```

**Expected Response:** Full result in HTTP response (may take 5-15 seconds)

### Test 2: Non-Blocking Mode (Webhook)

First, set up a webhook receiver (for testing):

```python
# test_webhook_receiver.py
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    print("📩 Received webhook:")
    print(body)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
```

Run the receiver:

```bash
python test_webhook_receiver.py
```

Send non-blocking request:

```bash
curl -X POST http://localhost:8000/a2a/agent/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-nonblocking-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "analyze ETH"}]
      },
      "configuration": {
        "blocking": false,
        "pushNotificationConfig": {
          "url": "http://localhost:9000/webhook",
          "token": "test-token-123",
          "authentication": {"schemes": ["Bearer"]}
        }
      }
    }
  }'
```

**Expected Response:** Immediate ACK with `{"result": null}`  
**Expected Webhook:** Full result sent to webhook URL after processing

---

## Troubleshooting

### Issue: Webhook Returns 400 Bad Request

**Cause:** Webhook payload format doesn't match what the client expects.

**Solution:**

1. Log the exact payload being sent:
   ```python
   print(f"Sending webhook payload: {json.dumps(payload, indent=2)}")
   ```
2. Compare with successful examples from other agents
3. Ensure you're sending a proper JSON-RPC response with `jsonrpc`, `id`, and either `result` or `error` (never both)

### Issue: Webhook Times Out

**Cause:** Processing takes too long, or webhook URL is unreachable.

**Solution:**

1. Increase timeout in `send_webhook_notification(timeout=60)`
2. Add retry logic:
   ```python
   for attempt in range(3):
       try:
           await send_webhook_notification(...)
           break
       except Exception as exc:
           if attempt == 2:
               raise
           await asyncio.sleep(2 ** attempt)  # exponential backoff
   ```

### Issue: Client Never Receives Webhook

**Cause:**

- Background task failed silently
- Webhook URL incorrect
- Network/firewall issues

**Solution:**

1. Add comprehensive logging in `_process_and_send_webhook()`
2. Test webhook URL independently with `curl` or Postman
3. Check Railway/server logs for errors
4. Use a webhook testing service like webhook.site for debugging

---

## Best Practices

1. **Always log webhook attempts** - Include URL, status, and response
2. **Implement timeouts** - Don't let webhook calls hang forever
3. **Add retry logic** - Network issues happen, retry 2-3 times with backoff
4. **Validate webhook config** - Check URL format before starting background task
5. **Monitor background tasks** - Track how many are running to avoid memory issues
6. **Use structured logging** - Include request_id in all log messages for tracing
7. **Test both modes** - Ensure blocking mode still works when adding webhook support
8. **Document webhook format** - Provide examples for clients integrating with your agent

---

## Environment Variables

Add these to your `.env` for webhook configuration:

```bash
# Webhook Settings (optional - only if your agent sends webhooks to external services)
NOTIFIER_WEBHOOK=https://your-notification-service.com/webhook
NOTIFIER_WEBHOOK_TOKEN=your-secret-token
ENABLE_NOTIFICATIONS=true
NOTIFICATION_COOLDOWN_SECONDS=900
```

---

## Summary

**Current Setup:** Blocking mode only (synchronous responses)

- ✅ Simple and reliable
- ✅ Easy to debug
- ✅ Works with all A2A clients
- ⚠️ Limited to ~30 second processing time

**With Webhooks:** Hybrid mode (blocking + non-blocking)

- ✅ Supports long-running operations (>30s)
- ✅ Better user experience (immediate ACK)
- ✅ Scalable for complex workflows
- ⚠️ More complex to implement and debug
- ⚠️ Requires client webhook support

**Recommendation:** Keep blocking mode for now. Only add webhooks when:

1. Processing consistently takes >20 seconds
2. You need to support very complex multi-step workflows
3. Your client platform fully supports webhook callbacks
