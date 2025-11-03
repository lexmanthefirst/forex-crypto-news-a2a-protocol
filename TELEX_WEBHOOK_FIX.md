# Telex.im Webhook 400 Error - FIXED ✅

## Problem
```
httpx.HTTPStatusError: Client error '400 Bad Request' for url 'https://ping.telex.im/v1/a2a/webhooks/...'
```

Telex.im was rejecting the webhook notification with a 400 Bad Request error.

## Root Cause

The webhook was sending the **TaskResult directly** instead of wrapping it in a **JSON-RPC response structure**.

### What Was Sent (WRONG ❌):
```json
{
  "id": "task-1762203817",
  "contextId": "context-1762203817",
  "status": { ... },
  "artifacts": [ ... ],
  "history": [ ... ],
  "kind": "task"
}
```

### What Telex.im Expected (CORRECT ✅):
```json
{
  "jsonrpc": "2.0",
  "id": "9e390bc16dd44ac0a8a62b787582b03d",
  "result": {
    "id": "task-1762203817",
    "contextId": "context-1762203817",
    "status": { ... },
    "artifacts": [ ... ],
    "history": [ ... ],
    "kind": "task"
  }
}
```

## The Fix

### Changed in `main.py`:

#### 1. Pass `request_id` to `_process_and_notify`:
```python
# Line ~206
asyncio.create_task(
    _process_and_notify(
        messages=messages,
        config=config,
        request_id=request_id,  # ✅ Added this
        webhook_url=config.pushNotificationConfig.url,
        webhook_token=config.pushNotificationConfig.token,
        webhook_auth=config.pushNotificationConfig.authentication
    )
)
```

#### 2. Wrap result in JSON-RPC response:
```python
# Line ~288
async def _process_and_notify(
    messages: list[A2AMessage],
    config: MessageConfiguration,
    request_id: str,  # ✅ Added parameter
    webhook_url: str,
    webhook_token: str | None = None,
    webhook_auth: dict[str, Any] | None = None,
) -> None:
    """Process request in background and send result via webhook."""
    try:
        # Process the request
        result = await _process_with_agent(messages, config=config)
        
        # ✅ Wrap result in JSON-RPC response (required by Telex.im)
        response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
        
        # Send JSON-RPC response to webhook
        await send_webhook_notification(
            url=webhook_url,
            payload=response.model_dump(),  # ✅ Send full response
            token=webhook_token,
            auth=webhook_auth
        )
        print(f"DEBUG: Successfully sent result to webhook: {webhook_url}")
    except Exception as exc:
        print(f"DEBUG: Failed to process and notify: {exc}")
        traceback.print_exc()
        
        # ✅ Also added error handling to send errors via webhook
        try:
            error_response = create_error_response(
                request_id=request_id,
                code=A2AErrorCode.INTERNAL_ERROR,
                message="Internal error",
                data={"details": str(exc)}
            )
            await send_webhook_notification(
                url=webhook_url,
                payload=error_response,
                token=webhook_token,
                auth=webhook_auth
            )
        except Exception:
            print("DEBUG: Failed to send error notification")
            traceback.print_exc()
```

## Why This Matters

### Telex.im Webhook Endpoint Requirements:
1. **Must** receive a valid JSON-RPC 2.0 response
2. **Must** include the original `id` from the request
3. **Must** have `jsonrpc: "2.0"` field
4. **Must** have either `result` or `error` field

### The Flow Now:
```
1. Telex sends request with id="9e390bc16dd44ac0a8a62b787582b03d"
2. Agent returns {"jsonrpc": "2.0", "id": "...", "result": null}
3. Agent processes in background
4. Agent sends to webhook:
   {
     "jsonrpc": "2.0",
     "id": "9e390bc16dd44ac0a8a62b787582b03d",  ✅ Same ID
     "result": { ... TaskResult ... }
   }
5. Telex accepts the webhook ✅
6. Message appears in chat ✅
```

## What About Other Platforms?

### For Your Own Website
If you're implementing your own webhook endpoint (not Telex.im), you have two options:

#### Option A: Accept JSON-RPC Format (Recommended)
```python
@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    
    # Extract the result from JSON-RPC wrapper
    result = payload.get("result")
    
    # Process the TaskResult
    await process_analysis(result)
```

#### Option B: Accept TaskResult Directly
You would need to modify the agent to detect your webhook URL and send unwrapped data:

```python
# In _process_and_notify
if webhook_url.startswith("https://your-website.com"):
    # Your website - send unwrapped
    await send_webhook_notification(
        url=webhook_url,
        payload=result.model_dump(),
        token=webhook_token,
        auth=webhook_auth
    )
else:
    # Standard (Telex.im) - send wrapped in JSON-RPC
    response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=result)
    await send_webhook_notification(
        url=webhook_url,
        payload=response.model_dump(),
        token=webhook_token,
        auth=webhook_auth
    )
```

**But we recommend Option A** - just accept JSON-RPC format everywhere for consistency!

## Testing

### Test 1: Telex.im Integration
1. Deploy your updated code to Railway
2. Chat with your agent on Telex.im
3. You should now see responses in the chat ✅

### Test 2: Local Test with Mock Webhook
```python
# test_webhook.py
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

@app.post("/webhook")
async def receive_webhook(request: Request):
    import json
    payload = await request.json()
    
    print("=" * 80)
    print("WEBHOOK RECEIVED:")
    print(json.dumps(payload, indent=2))
    print("=" * 80)
    
    # Verify JSON-RPC structure
    assert payload.get("jsonrpc") == "2.0"
    assert "id" in payload
    assert "result" in payload or "error" in payload
    
    print("✅ Valid JSON-RPC response!")
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
```

Run test:
```bash
# Terminal 1: Start mock webhook
python test_webhook.py

# Terminal 2: Expose with ngrok
ngrok http 5000

# Terminal 3: Send test request
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-123",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "role": "user",
        "parts": [{"kind": "text", "text": "Analyze BTC"}]
      },
      "configuration": {
        "blocking": false,
        "pushNotificationConfig": {
          "url": "https://your-ngrok-url.ngrok.io/webhook",
          "token": "test-token"
        }
      }
    }
  }'
```

Expected output in Terminal 1:
```json
================================================================================
WEBHOOK RECEIVED:
{
  "jsonrpc": "2.0",
  "id": "test-123",
  "result": {
    "id": "task-1762203817",
    "contextId": "context-1762203817",
    "status": {
      "state": "input-required",
      "timestamp": "2025-11-03T22:03:37.123456Z",
      "message": {
        "kind": "message",
        "role": "agent",
        "parts": [
          {
            "kind": "text",
            "text": "Analysis for BTC: direction=bearish confidence=0.70..."
          }
        ]
      }
    },
    "artifacts": [...],
    "history": [...],
    "kind": "task"
  }
}
================================================================================
✅ Valid JSON-RPC response!
```

## Deployment

### Push to Railway:
```bash
git add main.py
git commit -m "Fix: Wrap webhook payload in JSON-RPC response for Telex.im compatibility"
git push
```

Railway will automatically deploy the updated code.

## Verification

After deployment, check Railway logs:
```
✅ Should see: "DEBUG: Successfully sent result to webhook: https://ping.telex.im/..."
❌ Should NOT see: "httpx.HTTPStatusError: Client error '400 Bad Request'"
```

## Summary

| Before | After |
|--------|-------|
| ❌ Sent raw TaskResult to webhook | ✅ Sends JSON-RPC wrapped response |
| ❌ Telex.im rejected with 400 error | ✅ Telex.im accepts webhook |
| ❌ No messages in chat | ✅ Messages appear in chat |
| ❌ Missing request_id parameter | ✅ request_id properly tracked |
| ❌ No error webhook handling | ✅ Errors also sent via webhook |

## Related Files Modified
- ✅ `main.py` - Fixed `_handle_nonblocking_request` and `_process_and_notify`
- ℹ️ No changes needed to `models/a2a.py`
- ℹ️ No changes needed to `utils/notifier.py`
- ℹ️ No changes needed to `agents/market_agent.py`

**Status**: Ready to deploy! 🚀
