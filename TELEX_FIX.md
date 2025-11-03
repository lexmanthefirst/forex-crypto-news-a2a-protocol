# Telex.im Integration Fix

## Problem

Your agent was returning full responses immediately even for non-blocking requests, causing Telex.im to not receive messages in the chat.

## Root Cause

The field name mismatch: Telex.im sends `pushNotificationConfig` but your code expected `pushNotification`.

## Changes Made

### 1. **models/a2a.py** - Fixed field name

```python
# BEFORE
pushNotification: PushNotificationConfig | None = None

# AFTER
pushNotificationConfig: PushNotificationConfig | None = None
```

### 2. **main.py** - Updated webhook handling

- Changed condition to check `config.pushNotificationConfig` instead of `config.pushNotification`
- Updated `_process_and_notify()` to send **TaskResult directly** (not wrapped in JSON-RPC response)
- Removed `request_id` parameter (not needed for webhook)
- Added `webhook_auth` parameter for authentication

### 3. **utils/notifier.py** - Enhanced authentication

- Added `auth` parameter to support both token and auth dict
- Handles `Bearer` authentication scheme properly

## How It Works Now

### Non-Blocking Request Flow (Telex.im):

1. **Immediate Response**: Returns `{"jsonrpc": "2.0", "id": "...", "result": null}`
2. **Background Processing**: Agent processes the request asynchronously
3. **Webhook Delivery**: Sends `TaskResult` directly to `pushNotificationConfig.url`
4. **Telex Chat**: Receives the message and displays it

### Key Differences from Before:

- ✅ Returns `null` immediately for non-blocking requests
- ✅ Sends only `TaskResult` to webhook (not wrapped in JSON-RPC)
- ✅ Uses correct field name `pushNotificationConfig`
- ✅ Properly handles Bearer token authentication

## Testing

### 1. Start your agent:

```bash
python main.py
```

### 2. Test with Telex.im:

Just send a message to your agent in Telex chat. It should now respond properly.

### 3. Test locally (blocking mode):

```bash
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "role": "user",
        "parts": [{"kind": "text", "text": "Analyze BTC"}]
      }
    }
  }'
```

## Expected Behavior

### Blocking Request (blocking: true):

- Returns full TaskResult immediately
- No webhook call

### Non-Blocking Request (blocking: false with pushNotificationConfig):

- Returns `{"jsonrpc": "2.0", "id": "...", "result": null}` immediately
- Processes in background
- Sends TaskResult to webhook URL
- Telex.im displays the message in chat

## Debugging

If you still don't see responses:

1. Check your agent logs for `DEBUG: Successfully sent result to webhook`
2. Verify webhook URL is correct in Telex
3. Check if token authentication is working
4. Look for any exceptions in the terminal

## Summary

The fix ensures your agent properly implements the A2A protocol's non-blocking mode by:

- Using the correct field name from Telex.im
- Returning null immediately for async requests
- Sending unwrapped TaskResult to webhooks
- Supporting proper Bearer token authentication
