# Market Intelligence A2A Agent

A FastAPI-based Agent-to-Agent (A2A) protocol service that provides real-time cryptocurrency and forex market analysis using AI and technical indicators.

## Features

- Natural language market analysis for ANY cryptocurrency or forex pair
- **Comprehensive Market Summaries** - Get best/worst performers, trending coins, newly added tokens
- Dynamic symbol support - supports BTC, ETH, SOL, MATIC, PEPE, and hundreds more
- Automatic CoinGecko ID lookup for unknown crypto symbols
- AI-powered insights using Google Gemini
- Technical analysis with price trends, SMA, and volatility calculations
- Multi-source news aggregation (CryptoPanic, NewsAPI)
- Real-time price data from CoinGecko and AlphaVantage
- JSON-RPC 2.0 API endpoint
- Redis-based session storage
- Webhook notifications for automated alerts
- Docker deployment ready
- Integration with Telex.im platform

## Quick Start

### Prerequisites

- Python 3.13+
- Redis instance (or Redis Cloud account)
- API keys for: Gemini, CoinGecko, AlphaVantage, NewsAPI, CryptoPanic

### Installation

1. Clone the repository:

```bash
git clone https://github.com/lexmanthefirst/forex-crypto-news-a2a-protocol.git
cd forex-crypto-news-a2a-protocol
```

2. Install dependencies:

```bash
pip install -e .
```

3. Run the application:

```bash
uvicorn main:app --reload
```

The service will be available at `http://localhost:8000`

## Using Docker

### Build and run locally:

```bash
docker-compose up -d
```

### Pull from GitHub Container Registry:

```bash
docker pull ghcr.io/lexmanthefirst/forex-crypto-news-a2a-protocol:latest
docker run -p 8000:8000 --env-file .env ghcr.io/lexmanthefirst/forex-crypto-news-a2a-protocol:latest
```

## API Usage

### Health Check

```bash
curl http://localhost:8000/health
```

### Analyze a Market (JSON-RPC)

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

### Example Analysis Requests

The agent accepts natural language queries for ANY cryptocurrency or forex pair:

**Individual Asset Analysis:**

- "Analyze BTC" or "Analyze Bitcoin"
- "What's happening with PEPE?"
- "Give me a technical analysis of SOL"
- "Show me MATIC analysis"
- "Analyze Arbitrum" (automatically maps to ARB)
- "What about Dogecoin?"

**Forex Pairs:**

- "What's the outlook for EUR/USD?"
- "Analyze GBP/JPY"
- "Show me USD/CHF analysis"

**Market Summary Requests:**

- "Summarize crypto and forex movements today"
- "What's happening in the market?"
- "Show me market overview"
- "What are the best performing coins?"
- "What are the worst performers today?"
- "Show me trending cryptocurrencies"
- "What's the market status?"

The agent will automatically:

- Extract the symbol or pair from your query
- Look up the correct CoinGecko ID if needed
- Fetch real-time prices and 7-day history
- Generate AI-powered analysis with technical indicators

## Response Format

The API returns structured JSON-RPC 2.0 responses with:

- AI-generated analysis and insights
- Technical indicators (7-day trends, SMA, volatility)
- Recent news headlines
- Current price data
- Market sentiment and confidence scores

## Configuration

Key environment variables:

- `REDIS_URL`: Redis connection string
- `GEMINI_MODEL`: AI model to use (default: gemini-2.0-flash-exp)
- `WATCHLIST`: Comma-separated list of symbols to monitor
- `POLL_INTERVAL_MINUTES`: How often to run scheduled analysis
- `ENABLE_NOTIFICATIONS`: Enable/disable webhook notifications
- `NOTIFICATION_COOLDOWN_SECONDS`: Minimum time between notifications

## Integration with Telex.im

The agent supports the Telex.im A2A protocol with webhook-based non-blocking responses. See `a2a-config.json` for platform configuration.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
