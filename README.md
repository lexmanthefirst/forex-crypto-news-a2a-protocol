# Market Intelligence A2A Agent

Real-time cryptocurrency and forex analysis agent using the A2A protocol. Supports natural language queries, technical analysis, and AI-powered insights.

## Features

- **250+ cryptocurrencies** - Flexible name recognition (BTC, bitcoin, Bitcoin, etc.)
- **Forex pairs** - Real-time exchange rates (EUR/USD, GBP/JPY, etc.)
- **AI analysis** - Google Gemini-powered market insights
- **Technical indicators** - 7-day trends, SMA, volatility
- **News aggregation** - Multi-source crypto news
- **Conversation history** - Multi-turn conversations with context
- **Smart caching** - In-memory fallback when Redis is down
- **Intent classification** - Natural language understanding

## Quick Start

```bash
# Install
pip install -e .

# Run
uvicorn main:app --reload
```

## API Usage

```bash
curl -X POST http://localhost:8000/a2a/agent/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "What'\''s BTC doing?"}]
      }
    }
  }'
```

## Endpoints

- `POST /a2a/agent/market` - Main A2A protocol endpoint
- `GET /agent.json` - Agent capabilities and metadata
- `GET /health` - Health check

## Docker

```bash
docker-compose up -d
```

Or pull from GitHub Container Registry:

```bash
docker pull ghcr.io/lexmanthefirst/forex-crypto-news-a2a-protocol:latest
```
