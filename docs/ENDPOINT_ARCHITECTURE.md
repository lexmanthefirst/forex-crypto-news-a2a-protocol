# Market Summary Endpoint Architecture

## Current Implementation

The market summary functionality is currently integrated into the main A2A endpoint at `/a2a/market`. The agent automatically detects market summary requests based on keywords in the natural language query and routes them to the appropriate handler.

### How It Works Now

**Single Endpoint Pattern:**

```
POST /a2a/market
```

The agent uses intelligent routing:

1. User sends a natural language message
2. Agent detects if it's a market summary request (via keywords)
3. If yes → routes to `_handle_market_summary()`
4. If no → routes to individual asset analysis

**Example:**

```bash
# Market summary - automatically detected
POST /a2a/market
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"kind": "text", "text": "Summarize crypto movements today"}]
    }
  }
}

# Individual asset - automatically detected
POST /a2a/market
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"kind": "text", "text": "Analyze BTC"}]
    }
  }
}
```

## Proposed Separate Endpoint Architecture

### Option A: Dedicated Market Summary Endpoint

Create a separate REST endpoint specifically for market summaries:

```
GET /api/market/summary
POST /api/market/summary
```

**Advantages:**

- ✅ Clear separation of concerns
- ✅ Can return different response format (not bound to A2A protocol)
- ✅ Easier to cache (query string parameters)
- ✅ Simpler for non-A2A clients
- ✅ Can add query parameters for customization

**Query Parameters:**

```
GET /api/market/summary?
  limit=10                    # Number of top cryptos
  &include=trending,new       # What sections to include
  &timeframe=24h              # 24h, 7d, 30d
  &format=json                # json, text
```

**Example Implementation:**

```python
@app.get("/api/market/summary")
async def market_summary_endpoint(
    limit: int = 10,
    include: str = "all",  # all, trending, performers, new
    timeframe: str = "24h",
    format: str = "json"
):
    summary = await get_comprehensive_market_summary()

    if format == "text":
        return {"text": format_market_summary_text(summary)}

    return summary
```

### Option B: Extended A2A Method

Add a new JSON-RPC method to the existing A2A endpoint:

```
POST /a2a/market
{
  "jsonrpc": "2.0",
  "method": "market/summary",  // New method
  "params": {
    "limit": 10,
    "include": ["trending", "performers"],
    "timeframe": "24h"
  }
}
```

**Advantages:**

- ✅ Maintains A2A protocol consistency
- ✅ Single endpoint to manage
- ✅ Works with existing authentication/middleware
- ✅ Better for A2A agent-to-agent communication

**Implementation Changes Required:**

```python
# In main.py
if rpc.method == "message/send":
    # Existing natural language processing
    ...
elif rpc.method == "market/summary":
    # Direct market summary without NLP
    params = MarketSummaryParams(**rpc.params)
    return await handle_market_summary_direct(params)
```

### Option C: Hybrid Approach

Support both patterns:

1. **Natural Language** (current): POST /a2a/market with "message/send"
2. **Programmatic**: POST /a2a/market with "market/summary"
3. **REST API**: GET /api/market/summary

**Routing:**

```
/a2a/market + method="message/send" + NLP detection → Market summary
/a2a/market + method="market/summary" + params → Market summary
/api/market/summary + query params → Market summary
```

## Recommendation

**Keep current implementation + Add Option B (Extended A2A Method)**

### Why?

1. **Backward Compatible**: Natural language detection continues to work
2. **Programmatic Access**: Clients can explicitly request summaries without relying on NLP
3. **A2A Compliant**: Maintains protocol standards for agent communication
4. **Flexible**: Supports both human and machine interactions

### Proposed Implementation Plan

**Phase 1: Add explicit method (no breaking changes)**

```python
# New Pydantic model
class MarketSummaryParams(BaseModel):
    limit: int = 10
    include_sections: list[str] = ["all"]
    timeframe: str = "24h"
    format: str = "structured"  # structured, text

# Update main.py endpoint
if rpc.method == "market/summary":
    params = MarketSummaryParams(**rpc.params)
    summary = await get_comprehensive_market_summary()

    if params.format == "text":
        text = format_market_summary_text(summary)
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=rpc.id,
            result={"text": text, "data": summary}
        )
    else:
        response = JSONRPCResponse(
            jsonrpc="2.0",
            id=rpc.id,
            result=summary
        )

    return JSONResponse(content=response.model_dump())
```

**Phase 2 (Optional): Add REST endpoint**

```python
@app.get("/api/market/summary")
async def get_market_summary(
    limit: int = Query(10, description="Number of top cryptos"),
    sections: str = Query("all", description="Comma-separated: all,trending,performers,new"),
    timeframe: str = Query("24h", description="24h, 7d, 30d"),
):
    """REST endpoint for market summary (non-A2A clients)"""
    summary = await get_comprehensive_market_summary()
    return summary
```

## Use Cases by Endpoint Type

### Natural Language (Current)

**Best for:**

- Human users via chat interfaces (Telex.im)
- Exploratory queries
- Conversational agents
- Users who don't know exact parameters

**Example:**

```
"What's happening in crypto today?"
"Show me the best performers"
```

### Programmatic A2A Method

**Best for:**

- Agent-to-agent communication
- Scheduled/automated summaries
- Integration with other A2A agents
- Systems that need consistent data structure

**Example:**

```json
{
  "jsonrpc": "2.0",
  "method": "market/summary",
  "params": {
    "limit": 20,
    "include_sections": ["performers", "trending"],
    "timeframe": "7d"
  }
}
```

### REST Endpoint (If Added)

**Best for:**

- Traditional web/mobile apps
- Non-A2A clients
- Webhooks/integrations
- Caching/CDN friendly
- Quick prototyping

**Example:**

```
GET /api/market/summary?limit=20&sections=performers,trending&timeframe=7d
```

## Data Flow Comparison

### Current (NLP-based)

```
User Query → A2A Endpoint → NLP Detection → Market Agent → Summary Handler → Response
```

### With Explicit Method

```
JSON-RPC Call → A2A Endpoint → Method Router → Summary Handler → Response
```

### With REST Endpoint

```
HTTP GET → REST Handler → Summary Utility → JSON Response
```

## Caching Strategy

Regardless of endpoint approach, implement caching:

```python
# Redis cache key
cache_key = f"market:summary:{timeframe}:{limit}:{sections}"
cache_ttl = 300  # 5 minutes

# Check cache first
cached = await redis_store.get(cache_key)
if cached:
    return json.loads(cached)

# Fetch fresh data
summary = await get_comprehensive_market_summary()

# Cache result
await redis_store.setex(cache_key, cache_ttl, json.dumps(summary))
```

## Authentication & Rate Limiting

**If adding separate endpoints:**

1. **A2A Method**: Use existing A2A authentication (if any)
2. **REST Endpoint**: Consider:
   - API key authentication
   - Rate limiting (e.g., 60 requests/minute per IP)
   - Optional premium tier with higher limits

```python
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

@app.get("/api/market/summary")
async def get_market_summary(api_key: str = Depends(verify_api_key)):
    ...
```

## Performance Considerations

### Current Implementation

- Response time: 5-15 seconds (fetches data on demand)
- No caching (every request is fresh)
- Good for real-time needs

### With Caching

- First request: 5-15 seconds
- Cached requests: <100ms
- TTL: 5 minutes (configurable)
- Trade-off: Slightly stale data for better performance

### With Background Jobs

- Pre-generate summaries every 5 minutes
- Store in Redis
- All requests: <100ms
- Always slightly stale (max 5 minutes old)

## Migration Path

**If you decide to add separate endpoints:**

1. **Phase 1** (No breaking changes):

   - Keep current NLP-based routing
   - Add `market/summary` method to A2A endpoint
   - Document both approaches

2. **Phase 2** (Optional):

   - Add REST endpoint at `/api/market/summary`
   - Add API key authentication
   - Implement caching layer

3. **Phase 3** (Optional):
   - Add background job for pre-generation
   - Add WebSocket endpoint for streaming updates
   - Add GraphQL endpoint for flexible queries

## Conclusion

**Recommendation: Keep current implementation as-is**

The natural language detection works well and provides a seamless user experience. The single endpoint approach:

- ✅ Maintains simplicity
- ✅ Works perfectly for A2A protocol
- ✅ Requires no code changes
- ✅ Handles both individual assets and market summaries intelligently
- ✅ Aligns with conversational agent paradigm

**Only add separate endpoints if:**

- You need programmatic access without NLP overhead
- You want to support non-A2A clients
- You need fine-grained control over parameters
- You want to implement aggressive caching
- You have high-volume automated requests

The current architecture is elegant and sufficient for most use cases. The agent's intelligent routing eliminates the need for users to know which endpoint to call.
