# Webhook Notification Integration Guide

## Overview

This guide explains how to implement webhook notifications for your A2A Market Intelligence Agent on your own website (not Telex.im). The webhook system allows your agent to process requests asynchronously and send results back to your web application.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Use Cases](#use-cases)
3. [How It Works](#how-it-works)
4. [Implementation Steps](#implementation-steps)
5. [Code Examples](#code-examples)
6. [Security Considerations](#security-considerations)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Your Website  │         │   A2A Agent      │         │  Your Webhook   │
│   (Frontend)    │────1───▶│   (FastAPI)      │         │   Endpoint      │
└─────────────────┘         └──────────────────┘         └─────────────────┘
                                      │                            ▲
                                      │                            │
                                      │────────2───────────────────┘
                                      (Background Processing)

1. User makes request with webhook URL
2. Agent processes and POSTs result to webhook
```

### Flow:

1. **Request Phase**: Your website sends a POST request to `/a2a/market` with `blocking: false` and webhook configuration
2. **Immediate Response**: Agent returns `{"result": null}` immediately (non-blocking)
3. **Background Processing**: Agent processes the market analysis asynchronously
4. **Webhook Callback**: Agent POSTs the complete result to your webhook URL

---

## Use Cases

### 1. **Real-Time Market Dashboard**

- User requests "Analyze BTC" from your dashboard
- Shows "Processing..." spinner
- Receives webhook notification with analysis
- Updates dashboard with results in real-time

### 2. **Automated Trading Bot**

- Trading bot requests market analysis every 15 minutes
- Bot continues other operations while waiting
- Receives analysis via webhook
- Makes trading decisions based on results

### 3. **Mobile App Notifications**

- User requests analysis on mobile app
- App can close or switch to background
- Your webhook server receives result
- Sends push notification to user's device

### 4. **Batch Processing**

- Request analysis for 50 crypto assets
- Each request returns immediately
- Process all in parallel
- Receive 50 webhook callbacks as they complete

### 5. **Slack/Discord Bot Integration**

- User types "/analyze BTC" in Slack
- Bot sends request to A2A agent
- Bot responds "⏳ Analyzing..."
- Webhook updates Slack message with results

### 6. **Email Report Generation**

- Scheduled job requests daily market summary
- System continues other tasks
- Webhook receives complete analysis
- Generates and emails PDF report

---

## How It Works

### Current Implementation (Telex.im Mode)

The agent currently supports Telex.im's webhook pattern where:

- Telex sends `pushNotificationConfig` with webhook URL and token
- Agent uses those credentials dynamically per request

### For Your Own Website

You need to either:

1. **Use the same pattern** (send webhook config with each request)
2. **Configure static webhook** (set default webhook in environment variables)

---

## Implementation Steps

### Option 1: Dynamic Webhook (Same as Telex.im)

**Pros**: Flexible, different webhooks per request, no environment config
**Cons**: Must send webhook URL with every request

#### Step 1: Send Request with Webhook Config

```json
POST http://your-agent-domain.com/a2a/market
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": "request-123",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "Analyze BTC"
        }
      ]
    },
    "configuration": {
      "blocking": false,
      "acceptedOutputModes": ["text/plain", "application/json"],
      "pushNotificationConfig": {
        "url": "https://your-website.com/api/webhooks/market-analysis",
        "token": "your-secret-webhook-token-here",
        "authentication": {
          "schemes": ["Bearer"]
        }
      }
    }
  }
}
```

#### Step 2: Create Webhook Endpoint on Your Website

```python
# your-website/api/webhooks/market_analysis.py
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
import hmac
import hashlib

app = FastAPI()

WEBHOOK_SECRET = "your-secret-webhook-token-here"

@app.post("/api/webhooks/market-analysis")
async def receive_market_analysis(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Receive analysis results from A2A agent"""

    # Verify Bearer token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.replace("Bearer ", "")
    if token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Parse the result
    result = await request.json()

    # Extract data
    task_id = result.get("id")
    status = result.get("status", {})
    message = status.get("message")
    artifacts = result.get("artifacts", [])

    # Process the result
    # Option 1: Store in database
    await store_analysis_result(task_id, result)

    # Option 2: Send to WebSocket clients
    await broadcast_to_websocket_clients(result)

    # Option 3: Send push notification
    await send_push_notification(result)

    # Option 4: Update Slack/Discord
    await send_slack_message(format_analysis(result))

    return {"status": "received", "task_id": task_id}


async def store_analysis_result(task_id: str, result: dict):
    """Store result in your database"""
    # Your database logic here
    # Example: await db.analysis_results.insert_one(result)
    pass


async def broadcast_to_websocket_clients(result: dict):
    """Send to connected WebSocket clients for real-time updates"""
    # Your WebSocket logic here
    # Example: await websocket_manager.broadcast(result)
    pass


async def send_push_notification(result: dict):
    """Send mobile push notification"""
    # Your push notification logic here
    # Example: await firebase.send_notification(...)
    pass


async def send_slack_message(message: str):
    """Post to Slack channel"""
    # Your Slack integration here
    # Example: await slack_client.chat_postMessage(...)
    pass


def format_analysis(result: dict) -> str:
    """Format analysis for human reading"""
    status = result.get("status", {})
    message = status.get("message", {})
    parts = message.get("parts", [])

    if parts:
        text = parts[0].get("text", "")
        return f"📊 Market Analysis:\n{text}"

    return "Analysis completed"
```

### Option 2: Static Webhook Configuration

**Pros**: Simple, no need to send webhook with each request
**Cons**: Same webhook for all requests, requires code changes

#### Changes Required to `main.py`:

```python
# Add after line 52 (in lifespan function)
@asynccontextmanager
async def lifespan(_: FastAPI):
    global market_agent

    await redis_store.initialize()

    # Add static webhook configuration
    static_webhook_url = os.getenv("STATIC_WEBHOOK_URL")
    static_webhook_token = os.getenv("STATIC_WEBHOOK_TOKEN")

    market_agent = MarketAgent(
        static_webhook_url=static_webhook_url,
        static_webhook_token=static_webhook_token
    )

    poll_minutes = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
    scheduler.add_job(_scheduled_analysis_job, "interval", minutes=poll_minutes)
    scheduler.start()
    yield
    shutdown_result = scheduler.shutdown()
    if asyncio.iscoroutine(shutdown_result):
        await cast(Awaitable[Any], shutdown_result)
    await redis_store.close()
    market_agent = None
```

```python
# Modify _handle_nonblocking_request (around line 206)
async def _handle_nonblocking_request(
    request_id: str,
    messages: list[A2AMessage],
    config: MessageConfiguration
) -> JSONResponse:
    """Handle non-blocking request - send immediate ACK and process in background."""
    # Send immediate acknowledgment with null result
    ack_response = JSONRPCResponse(jsonrpc="2.0", id=request_id, result=None)

    # Determine webhook URL and token
    webhook_url = None
    webhook_token = None
    webhook_auth = None

    # Priority 1: Use webhook from request (Telex.im pattern)
    if config.pushNotificationConfig:
        webhook_url = config.pushNotificationConfig.url
        webhook_token = config.pushNotificationConfig.token
        webhook_auth = config.pushNotificationConfig.authentication
    # Priority 2: Use static webhook from environment
    elif market_agent and hasattr(market_agent, 'static_webhook_url'):
        webhook_url = market_agent.static_webhook_url
        webhook_token = market_agent.static_webhook_token

    # Only process if webhook is configured
    if webhook_url:
        asyncio.create_task(
            _process_and_notify(
                messages=messages,
                config=config,
                webhook_url=webhook_url,
                webhook_token=webhook_token,
                webhook_auth=webhook_auth
            )
        )
    else:
        print("WARNING: Non-blocking request received but no webhook configured")

    return JSONResponse(content=ack_response.model_dump())
```

#### Changes Required to `agents/market_agent.py`:

```python
# Modify __init__ method (around line 27)
def __init__(
    self,
    notifier_webhook: str | None = None,
    notifier_webhook_token: str | None = None,
    enable_notifications: bool | None = None,
    static_webhook_url: str | None = None,  # NEW
    static_webhook_token: str | None = None  # NEW
):
    self.notifier_webhook = notifier_webhook
    self.notifier_webhook_token = notifier_webhook_token
    self.enable_notifications = enable_notifications if enable_notifications is not None else os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"
    self.static_webhook_url = static_webhook_url  # NEW
    self.static_webhook_token = static_webhook_token  # NEW
```

#### Environment Variables (.env):

```bash
# Static webhook configuration (Option 2)
STATIC_WEBHOOK_URL=https://your-website.com/api/webhooks/market-analysis
STATIC_WEBHOOK_TOKEN=your-secret-webhook-token-here
```

---

## Code Examples

### Frontend: Making Request with Loading State

```javascript
// React example
import React, { useState } from "react";

function MarketAnalysis() {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [requestId, setRequestId] = useState(null);

  const analyzeMarket = async (symbol) => {
    setLoading(true);
    const reqId = `req-${Date.now()}`;
    setRequestId(reqId);

    // Send request to A2A agent
    await fetch("https://your-agent.com/a2a/market", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: reqId,
        method: "message/send",
        params: {
          message: {
            kind: "message",
            role: "user",
            parts: [{ kind: "text", text: `Analyze ${symbol}` }],
          },
          configuration: {
            blocking: false,
            pushNotificationConfig: {
              url: "https://your-website.com/api/webhooks/market-analysis",
              token: "your-webhook-token",
            },
          },
        },
      }),
    });

    // Result will arrive via webhook
    // WebSocket or polling will update UI
  };

  // WebSocket listener for real-time updates
  React.useEffect(() => {
    const ws = new WebSocket("wss://your-website.com/ws");

    ws.onmessage = (event) => {
      const result = JSON.parse(event.data);
      if (result.requestId === requestId) {
        setAnalysis(result);
        setLoading(false);
      }
    };

    return () => ws.close();
  }, [requestId]);

  return (
    <div>
      <button onClick={() => analyzeMarket("BTC")}>Analyze Bitcoin</button>

      {loading && <div>⏳ Analyzing market...</div>}

      {analysis && (
        <div className="analysis-result">
          <h3>Market Analysis</h3>
          <p>{analysis.status.message.parts[0].text}</p>
        </div>
      )}
    </div>
  );
}
```

### Backend: WebSocket Broadcast

```python
# websocket_manager.py
from fastapi import WebSocket
from typing import List

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                # Handle disconnected clients
                self.disconnect(connection)

manager = WebSocketManager()

# In your webhook endpoint:
@app.post("/api/webhooks/market-analysis")
async def receive_market_analysis(request: Request, authorization: str = Header(None)):
    # ... authentication ...

    result = await request.json()

    # Broadcast to all connected clients
    await manager.broadcast({
        "type": "market_analysis",
        "requestId": result.get("id"),
        "data": result
    })

    return {"status": "received"}

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except:
        manager.disconnect(websocket)
```

### Database Storage

```python
# models.py
from sqlalchemy import Column, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(String, primary_key=True)
    task_id = Column(String, unique=True, index=True)
    symbol = Column(String, index=True)
    direction = Column(String)  # bullish, bearish, neutral
    confidence = Column(Float)
    result_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    webhook_received_at = Column(DateTime)

# In webhook handler:
async def store_analysis_result(task_id: str, result: dict):
    from database import SessionLocal

    # Extract data from artifacts
    analysis_artifact = next(
        (a for a in result.get("artifacts", []) if a.get("name") == "analysis"),
        None
    )

    if analysis_artifact:
        analysis_data = analysis_artifact["parts"][0]["data"]

        db = SessionLocal()
        db_result = AnalysisResult(
            id=str(uuid.uuid4()),
            task_id=task_id,
            symbol=extract_symbol_from_result(result),
            direction=analysis_data.get("direction"),
            confidence=analysis_data.get("confidence"),
            result_data=result,
            webhook_received_at=datetime.utcnow()
        )
        db.add(db_result)
        db.commit()
        db.close()
```

---

## Security Considerations

### 1. **Authentication**

Always verify the webhook token:

```python
import hmac
import hashlib

def verify_webhook_token(provided_token: str, expected_token: str) -> bool:
    """Constant-time comparison to prevent timing attacks"""
    return hmac.compare_digest(provided_token, expected_token)

@app.post("/api/webhooks/market-analysis")
async def receive_market_analysis(
    request: Request,
    authorization: str = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.replace("Bearer ", "")
    if not verify_webhook_token(token, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid token")

    # Process webhook...
```

### 2. **HTTPS Only**

```python
# Enforce HTTPS for webhook URLs
def validate_webhook_url(url: str) -> bool:
    return url.startswith("https://")

# In main.py, before sending webhook:
if not validate_webhook_url(webhook_url):
    raise ValueError("Webhook URL must use HTTPS")
```

### 3. **Rate Limiting**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/webhooks/market-analysis")
@limiter.limit("100/minute")  # Max 100 webhooks per minute
async def receive_market_analysis(request: Request):
    # Process webhook...
```

### 4. **Signature Verification** (Advanced)

```python
# When sending request, include signature
import hmac
import hashlib
import json

def generate_signature(payload: dict, secret: str) -> str:
    """Generate HMAC signature of payload"""
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    signature = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return signature

# In webhook handler, verify signature:
def verify_signature(payload: dict, signature: str, secret: str) -> bool:
    expected = generate_signature(payload, secret)
    return hmac.compare_digest(signature, expected)
```

### 5. **Timeout Protection**

```python
# In webhook handler
import asyncio

@app.post("/api/webhooks/market-analysis")
async def receive_market_analysis(request: Request):
    try:
        # Timeout after 5 seconds
        async with asyncio.timeout(5):
            result = await request.json()
            await process_result(result)
        return {"status": "received"}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Processing timeout")
```

---

## Testing

### Test 1: Local Testing with ngrok

```bash
# Terminal 1: Start your webhook server
python webhook_server.py

# Terminal 2: Expose via ngrok
ngrok http 5000

# Terminal 3: Test the flow
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
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

### Test 2: Mock Webhook Server

```python
# test_webhook_server.py
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

@app.post("/webhook")
async def receive_webhook(request: Request):
    result = await request.json()
    print("=" * 80)
    print("WEBHOOK RECEIVED:")
    print(json.dumps(result, indent=2))
    print("=" * 80)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
```

### Test 3: Integration Test

```python
# test_webhook_integration.py
import pytest
import httpx
import asyncio
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_webhook_flow():
    webhook_received = asyncio.Event()
    webhook_data = {}

    # Mock webhook endpoint
    @app.post("/test-webhook")
    async def mock_webhook(request: Request):
        nonlocal webhook_data
        webhook_data = await request.json()
        webhook_received.set()
        return {"status": "ok"}

    # Send request to agent
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/a2a/market",
            json={
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
                        "blocking": False,
                        "pushNotificationConfig": {
                            "url": "http://localhost:8000/test-webhook",
                            "token": "test-token"
                        }
                    }
                }
            }
        )

    # Should return null immediately
    assert response.json()["result"] is None

    # Wait for webhook (with timeout)
    await asyncio.wait_for(webhook_received.wait(), timeout=30)

    # Verify webhook data
    assert webhook_data["kind"] == "task"
    assert "status" in webhook_data
    assert "artifacts" in webhook_data
```

---

## Troubleshooting

### Issue 1: Webhook Not Receiving Data

**Symptoms**: Request returns null but webhook never receives result

**Debugging**:

```python
# Add to _process_and_notify in main.py
print(f"DEBUG: Starting webhook notification to {webhook_url}")
print(f"DEBUG: Token present: {webhook_token is not None}")
print(f"DEBUG: Result ID: {result.id}")
```

**Common Causes**:

- Firewall blocking outbound connections
- Webhook URL not accessible from agent server
- SSL certificate issues (use `verify=False` for testing only)

**Solution**:

```python
# In utils/notifier.py, add debugging:
async def send_webhook_notification(
    url: str,
    payload: Mapping[str, Any],
    token: str | None = None,
    auth: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> None:
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif auth and auth.get("schemes") == ["Bearer"]:
        if "credentials" in auth:
            headers["Authorization"] = f"Bearer {auth['credentials']}"

    print(f"DEBUG: Sending webhook to {url}")
    print(f"DEBUG: Headers: {headers}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=dict(payload), headers=headers)
            print(f"DEBUG: Webhook response status: {response.status_code}")
            response.raise_for_status()
        except Exception as e:
            print(f"ERROR: Webhook failed: {e}")
            raise
```

### Issue 2: Authentication Failures

**Symptoms**: Webhook endpoint returns 401 Unauthorized

**Check**:

1. Token is being sent: `print(f"Token: {webhook_token}")`
2. Header format is correct: `Authorization: Bearer <token>`
3. Token matches on both sides

**Solution**:

```python
# Temporarily log token (remove in production!)
print(f"DEBUG: Sending token: {webhook_token}")
```

### Issue 3: Slow Processing

**Symptoms**: Webhook takes too long to receive data

**Monitor**:

```python
import time

async def _process_and_notify(...):
    start = time.time()

    result = await _process_with_agent(messages, config=config)
    processing_time = time.time() - start
    print(f"DEBUG: Processing took {processing_time:.2f}s")

    webhook_start = time.time()
    await send_webhook_notification(...)
    webhook_time = time.time() - webhook_start
    print(f"DEBUG: Webhook send took {webhook_time:.2f}s")
```

### Issue 4: Duplicate Webhooks

**Symptoms**: Receiving multiple webhook calls for same request

**Solution**: Add deduplication in webhook handler:

```python
from cachetools import TTLCache

# Cache to track processed requests (TTL = 5 minutes)
processed_requests = TTLCache(maxsize=1000, ttl=300)

@app.post("/api/webhooks/market-analysis")
async def receive_market_analysis(request: Request):
    result = await request.json()
    task_id = result.get("id")

    # Check if already processed
    if task_id in processed_requests:
        print(f"DEBUG: Duplicate webhook for {task_id}, ignoring")
        return {"status": "duplicate"}

    # Mark as processed
    processed_requests[task_id] = True

    # Process normally
    await process_result(result)
    return {"status": "received"}
```

---

## Complete Example: Simple Dashboard

### File Structure

```
your-website/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── webhooks.py          # Webhook handlers
│   ├── websocket_manager.py # WebSocket manager
│   └── requirements.txt
└── frontend/
    ├── index.html
    └── app.js
```

### Backend (`backend/main.py`):

```python
from fastapi import FastAPI, WebSocket, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import httpx

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connections
active_connections = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except:
        active_connections.remove(websocket)

@app.post("/api/analyze")
async def analyze_market(symbol: str):
    """Trigger market analysis"""
    request_id = f"web-{symbol}-{int(time.time())}"

    # Send to A2A agent
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/a2a/market",
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "kind": "message",
                        "role": "user",
                        "parts": [{"kind": "text", "text": f"Analyze {symbol}"}]
                    },
                    "configuration": {
                        "blocking": False,
                        "pushNotificationConfig": {
                            "url": "http://localhost:5000/webhook",
                            "token": "my-secret-token"
                        }
                    }
                }
            }
        )

    return {"status": "processing", "request_id": request_id}

@app.post("/webhook")
async def receive_webhook(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Receive analysis from A2A agent"""
    # Verify token
    if not authorization or authorization != "Bearer my-secret-token":
        raise HTTPException(status_code=401)

    result = await request.json()

    # Broadcast to all WebSocket clients
    for conn in active_connections:
        try:
            await conn.send_json({
                "type": "analysis_result",
                "data": result
            })
        except:
            active_connections.remove(conn)

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
```

### Frontend (`frontend/index.html`):

```html
<!DOCTYPE html>
<html>
  <head>
    <title>Market Analysis Dashboard</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        max-width: 800px;
        margin: 50px auto;
      }
      .loading {
        color: orange;
      }
      .result {
        background: #f0f0f0;
        padding: 20px;
        margin: 20px 0;
        border-radius: 8px;
      }
      button {
        padding: 10px 20px;
        font-size: 16px;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <h1>📊 Market Analysis Dashboard</h1>

    <div>
      <input
        type="text"
        id="symbol"
        placeholder="Enter symbol (BTC, ETH, etc.)"
      />
      <button onclick="analyzeMarket()">Analyze</button>
    </div>

    <div id="status"></div>
    <div id="results"></div>

    <script>
      const ws = new WebSocket("ws://localhost:5000/ws");

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "analysis_result") {
          displayResult(data.data);
        }
      };

      async function analyzeMarket() {
        const symbol = document.getElementById("symbol").value;
        document.getElementById("status").innerHTML =
          '<p class="loading">⏳ Analyzing...</p>';

        const response = await fetch(
          `http://localhost:5000/api/analyze?symbol=${symbol}`,
          {
            method: "POST",
          }
        );

        const data = await response.json();
        console.log("Request sent:", data.request_id);
      }

      function displayResult(result) {
        document.getElementById("status").innerHTML = "";

        const status = result.status || {};
        const message = status.message || {};
        const parts = message.parts || [];

        let html = '<div class="result">';
        html += "<h3>✅ Analysis Complete</h3>";

        if (parts.length > 0) {
          html += `<p>${parts[0].text}</p>`;
        }

        html += "</div>";

        document.getElementById("results").innerHTML = html;
      }
    </script>
  </body>
</html>
```

---

## Summary

### Key Points

1. **Non-blocking mode** allows your website to remain responsive
2. **Webhook callbacks** deliver results asynchronously
3. **Two approaches**: Dynamic (per-request config) or Static (environment config)
4. **Security**: Always use HTTPS, verify tokens, implement rate limiting
5. **Real-time updates**: Use WebSockets to push results to frontend

### Next Steps

1. Choose your approach (dynamic or static webhook)
2. Implement webhook endpoint on your website
3. Add authentication and security measures
4. Test with ngrok or local environment
5. Deploy and monitor webhook reliability

### Best Practices

- ✅ Use HTTPS for webhook URLs
- ✅ Verify bearer tokens
- ✅ Implement request deduplication
- ✅ Add timeout handling
- ✅ Log webhook failures
- ✅ Store results in database
- ✅ Broadcast to WebSocket clients for real-time updates
- ✅ Monitor webhook latency and failures

---

## Support & Resources

- **Current Code**: No changes needed, current implementation supports webhooks
- **Testing Tool**: Use `test_webhook_server.py` for local testing
- **Debugging**: Enable DEBUG logs in `_process_and_notify` function
- **Security**: Review authentication section before production deployment
