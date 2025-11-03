# Building a Market Intelligence Agent with A2A Protocol: Step-by-Step Tutorial

This tutorial will guide you through building a simplified version of the Market Intelligence A2A Agent. We'll focus on the core concepts without the complexity of the full production system.

## What We'll Build

A minimal A2A agent that:

- Accepts natural language queries via JSON-RPC 2.0
- Fetches cryptocurrency prices from CoinGecko
- Returns structured analysis responses
- Follows the A2A protocol specification

## Prerequisites

- Python 3.11 or higher
- Basic understanding of FastAPI
- API key from CoinGecko (free tier is fine)

## Project Structure

```
simple-a2a-market-agent/
├── main.py                 # FastAPI application and endpoint
├── models.py              # Pydantic models for A2A protocol
├── agent.py               # Core agent logic
├── .env                   # Environment variables
└── requirements.txt       # Python dependencies
```

## Step 1: Setup Project

### Create Project Directory

```bash
mkdir simple-a2a-market-agent
cd simple-a2a-market-agent
```

### Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Install Dependencies

Create `requirements.txt`:

```txt
fastapi==0.115.0
uvicorn==0.30.0
pydantic==2.8.0
httpx==0.27.0
python-dotenv==1.0.0
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Configure Environment

Create `.env` file:

```env
COINGECKO_API_KEY=your_api_key_here
PORT=8000
```

## Step 2: Define A2A Protocol Models

Create `models.py`:

```python
from pydantic import BaseModel
from typing import Any, Literal


class MessagePart(BaseModel):
    """A part of an A2A message (text or data)."""
    kind: Literal["text", "data"]
    text: str | None = None
    data: dict[str, Any] | None = None


class A2AMessage(BaseModel):
    """A message in the A2A protocol."""
    role: Literal["user", "agent", "system"]
    parts: list[MessagePart]


class TaskStatus(BaseModel):
    """Status of a task execution."""
    state: Literal["completed", "failed", "running", "input-required"]
    message: A2AMessage | None = None


class Artifact(BaseModel):
    """An artifact containing results or data."""
    name: str
    parts: list[MessagePart]


class TaskResult(BaseModel):
    """Result of task execution."""
    id: str
    contextId: str
    status: TaskStatus
    artifacts: list[Artifact] = []
    history: list[A2AMessage] = []


class MessageConfiguration(BaseModel):
    """Configuration for message handling."""
    blocking: bool = True


class MessageParams(BaseModel):
    """Parameters for message/send method."""
    message: A2AMessage
    configuration: MessageConfiguration = MessageConfiguration()


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""
    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    method: str
    params: MessageParams


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""
    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    result: TaskResult | None = None
    error: dict[str, Any] | None = None
```

## Step 3: Build the Agent

Create `agent.py`:

```python
import re
import httpx
from datetime import datetime, timezone
from models import A2AMessage, Artifact, MessagePart, TaskResult, TaskStatus


class MarketAgent:
    """Simple market intelligence agent."""

    def __init__(self, coingecko_api_key: str):
        self.api_key = coingecko_api_key
        self.base_url = "https://api.coingecko.com/api/v3"

    async def process_message(self, message: A2AMessage) -> TaskResult:
        """Process a user message and return analysis."""

        # Extract text from message
        text = self._extract_text(message)
        print(f"Processing: {text}")

        # Extract crypto symbol (e.g., BTC, ETH)
        symbol = self._extract_symbol(text)

        if not symbol:
            return self._create_error_result(
                "Could not identify cryptocurrency. Please specify a symbol like BTC, ETH, SOL."
            )

        # Fetch price data
        price_data = await self._fetch_price(symbol)

        if not price_data:
            return self._create_error_result(
                f"Could not fetch price data for {symbol}"
            )

        # Create response
        return self._create_success_result(symbol, price_data)

    def _extract_text(self, message: A2AMessage) -> str:
        """Extract text from message parts."""
        texts = []
        for part in message.parts:
            if part.kind == "text" and part.text:
                texts.append(part.text)
        return " ".join(texts)

    def _extract_symbol(self, text: str) -> str | None:
        """Extract crypto symbol from text."""
        # Common crypto symbols
        crypto_map = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "cardano": "ADA",
            "dogecoin": "DOGE",
        }

        text_lower = text.lower()

        # Check for full names
        for name, symbol in crypto_map.items():
            if name in text_lower:
                return symbol

        # Check for symbols (2-5 uppercase letters)
        match = re.search(r"\b([A-Z]{2,5})\b", text.upper())
        if match:
            return match.group(1)

        return None

    async def _fetch_price(self, symbol: str) -> dict | None:
        """Fetch price data from CoinGecko."""
        # Map symbols to CoinGecko IDs
        coin_ids = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
            "ADA": "cardano",
            "DOGE": "dogecoin",
        }

        coin_id = coin_ids.get(symbol, symbol.lower())

        url = f"{self.base_url}/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24h_change": "true",
            "include_market_cap": "true",
        }

        if self.api_key:
            params["x_cg_demo_api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            if coin_id in data:
                return {
                    "symbol": symbol,
                    "price": data[coin_id].get("usd"),
                    "change_24h": data[coin_id].get("usd_24h_change"),
                    "market_cap": data[coin_id].get("usd_market_cap"),
                }
        except Exception as e:
            print(f"Error fetching price: {e}")

        return None

    def _create_success_result(self, symbol: str, price_data: dict) -> TaskResult:
        """Create a successful task result."""
        price = price_data["price"]
        change = price_data["change_24h"]
        market_cap = price_data["market_cap"]

        # Determine sentiment
        if change > 5:
            sentiment = "very bullish"
        elif change > 2:
            sentiment = "bullish"
        elif change > -2:
            sentiment = "neutral"
        elif change > -5:
            sentiment = "bearish"
        else:
            sentiment = "very bearish"

        # Create response text
        response_text = (
            f"**Analysis for {symbol}**\n\n"
            f"Current Price: ${price:,.2f}\n"
            f"24h Change: {change:+.2f}%\n"
            f"Market Cap: ${market_cap:,.0f}\n"
            f"Sentiment: {sentiment.title()}\n\n"
            f"The market is showing {sentiment} signals for {symbol}."
        )

        # Create A2A message
        agent_message = A2AMessage(
            role="agent",
            parts=[
                MessagePart(kind="text", text=response_text),
                MessagePart(kind="data", data={
                    "symbol": symbol,
                    "analysis": {
                        "price": price,
                        "change_24h": change,
                        "market_cap": market_cap,
                        "sentiment": sentiment,
                    }
                })
            ]
        )

        # Create artifact
        artifact = Artifact(
            name="price_analysis",
            parts=[MessagePart(kind="data", data=price_data)]
        )

        # Create task result
        return TaskResult(
            id=f"task-{int(datetime.now(timezone.utc).timestamp())}",
            contextId=f"context-{symbol.lower()}",
            status=TaskStatus(state="completed", message=agent_message),
            artifacts=[artifact],
            history=[agent_message]
        )

    def _create_error_result(self, error_message: str) -> TaskResult:
        """Create an error task result."""
        agent_message = A2AMessage(
            role="agent",
            parts=[MessagePart(kind="text", text=error_message)]
        )

        return TaskResult(
            id=f"task-{int(datetime.now(timezone.utc).timestamp())}",
            contextId="error",
            status=TaskStatus(state="failed", message=agent_message),
            artifacts=[],
            history=[agent_message]
        )
```

## Step 4: Create FastAPI Application

Create `main.py`:

```python
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from agent import MarketAgent
from models import JSONRPCRequest, JSONRPCResponse

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Simple Market Intelligence A2A Agent",
    description="A minimal A2A agent for cryptocurrency price analysis",
    version="1.0.0"
)

# Initialize agent
agent = MarketAgent(coingecko_api_key=os.getenv("COINGECKO_API_KEY", ""))


@app.post("/a2a/market")
async def a2a_endpoint(request: Request):
    """Main A2A protocol endpoint."""

    try:
        # Parse JSON-RPC request
        body = await request.json()
        rpc_request = JSONRPCRequest(**body)

        print(f"Received method: {rpc_request.method}")

        # Process message
        if rpc_request.method == "message/send":
            result = await agent.process_message(rpc_request.params.message)

            # Create JSON-RPC response
            response = JSONRPCResponse(
                jsonrpc="2.0",
                id=rpc_request.id,
                result=result
            )

            return JSONResponse(content=response.model_dump())

        else:
            # Unsupported method
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": rpc_request.id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {rpc_request.method}"
                    }
                }
            )

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": "unknown",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
        )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "agent": "Market Intelligence A2A"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
```

## Step 5: Run the Agent

### Start the Server

```bash
python main.py
```

You should see:

```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Test the Health Check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "agent": "Market Intelligence A2A"
}
```

### Test the A2A Endpoint

```bash
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [
          {
            "kind": "text",
            "text": "Analyze Bitcoin"
          }
        ]
      }
    }
  }'
```

Expected response:

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "id": "task-1699024800",
    "contextId": "context-btc",
    "status": {
      "state": "completed",
      "message": {
        "role": "agent",
        "parts": [
          {
            "kind": "text",
            "text": "**Analysis for BTC**\n\nCurrent Price: $67,543.21\n24h Change: +3.45%\nMarket Cap: $1,320,456,789,012\nSentiment: Bullish\n\nThe market is showing bullish signals for BTC."
          },
          {
            "kind": "data",
            "data": {
              "symbol": "BTC",
              "analysis": {
                "price": 67543.21,
                "change_24h": 3.45,
                "market_cap": 1320456789012,
                "sentiment": "bullish"
              }
            }
          }
        ]
      }
    },
    "artifacts": [
      {
        "name": "price_analysis",
        "parts": [...]
      }
    ],
    "history": [...]
  }
}
```

## Step 6: Understanding the Code

### A2A Protocol Flow

1. **Client sends JSON-RPC request** with method `message/send`
2. **Agent receives message** and extracts text
3. **Agent identifies symbol** (e.g., "Bitcoin" → "BTC")
4. **Agent fetches price data** from CoinGecko API
5. **Agent creates analysis** with sentiment
6. **Agent returns TaskResult** with structured data

### Key Components

**MessagePart**: Building block of messages

- Can be "text" (human-readable) or "data" (structured)

**A2AMessage**: Container for message parts

- Has a role: "user", "agent", or "system"

**TaskResult**: The agent's response

- Contains status, artifacts, and history
- Follows A2A protocol specification

**Artifact**: Package of results

- Named container for data
- Can include multiple parts

### What Makes It A2A?

✅ **JSON-RPC 2.0**: Standard protocol for method calls  
✅ **Structured Messages**: MessagePart with text and data  
✅ **Task-Based**: Returns TaskResult with status  
✅ **Artifacts**: Results packaged as reusable artifacts  
✅ **History**: Maintains conversation context

## Step 7: Testing Different Queries

Try these queries:

### Query Bitcoin

```bash
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"What is Bitcoin doing?"}]}}}'
```

### Query Ethereum

```bash
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Analyze ETH"}]}}}'
```

### Query Solana

```bash
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"3","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"How is SOL performing?"}]}}}'
```

## What We've Built

A minimal but functional A2A agent that:

✅ Accepts natural language queries  
✅ Extracts cryptocurrency symbols  
✅ Fetches real-time price data  
✅ Analyzes market sentiment  
✅ Returns structured A2A responses  
✅ Follows JSON-RPC 2.0 protocol

## Extending the Agent

From here, you can add:

1. **More Data Sources**: News APIs, technical indicators
2. **AI Analysis**: Integrate Google Gemini or OpenAI
3. **Caching**: Add Redis for performance
4. **Forex Support**: Add currency pair analysis
5. **Webhooks**: Support non-blocking requests
6. **Authentication**: Add API key validation
7. **Rate Limiting**: Prevent abuse
8. **Logging**: Track requests and errors

## Production Considerations

For production deployment:

- Add error handling and validation
- Implement proper logging
- Use environment-based configuration
- Add health checks and monitoring
- Implement rate limiting
- Secure API keys
- Add CORS configuration
- Use production-grade server (gunicorn)
- Deploy with Docker
- Set up CI/CD pipeline

## Conclusion

You've built a working A2A agent! This simple implementation demonstrates the core concepts:

- **Protocol Compliance**: JSON-RPC 2.0 and A2A message structure
- **Natural Language**: Extract intent from user messages
- **External APIs**: Fetch real-time data
- **Structured Responses**: Return data in A2A format

The full production version adds technical analysis, AI-powered insights, multiple data sources, and robust error handling, but the core architecture remains the same.

## Resources

- [A2A Protocol Specification](https://a2a.org)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [CoinGecko API](https://www.coingecko.com/en/api)
- [Full Project Repository](https://github.com/lexmanthefirst/forex-crypto-news-a2a-protocol)

Happy coding! 🚀
