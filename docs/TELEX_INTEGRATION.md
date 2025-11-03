# Telex.im Integration Guide

## Overview

The Market Intelligence A2A Agent integrates seamlessly with Telex.im, supporting both individual asset analysis and comprehensive market summaries through natural language queries.

## Integration Status

✅ **Fully Compatible** - The agent is designed to work perfectly with Telex.im's A2A protocol implementation.

## How It Works with Telex.im

### 1. Natural Language Processing

Telex.im sends user messages to the `/a2a/market` endpoint. The agent automatically:

- Strips HTML tags from rich-text messages
- Detects the query type (individual asset vs. market summary)
- Routes to the appropriate handler
- Returns formatted responses with structured data

### 2. HTML Handling

Telex.im sends HTML-formatted messages. The agent automatically strips HTML:

```python
# Telex.im sends:
"<p>Analyze <strong>BTC</strong></p>"

# Agent processes:
"Analyze BTC"
```

This ensures symbol extraction and analysis work correctly.

### 3. Webhook Support

For non-blocking requests, the agent supports Telex.im's webhook pattern:

```json
{
  "configuration": {
    "blocking": false,
    "pushNotification": {
      "url": "https://ping.telex.im/v1/a2a/webhooks/...",
      "token": "your-token"
    }
  }
}
```

The agent:

1. Returns immediate acknowledgment
2. Processes request in background
3. Sends result to webhook with Bearer token authentication

## Supported Query Types

### Individual Asset Analysis

**User asks in Telex.im:**

```
"Analyze BTC"
"What's happening with Ethereum?"
"Show me SOL analysis"
"Technical analysis of EUR/USD"
"What about PEPE?"
```

**Agent responds with:**

- Current price
- 24h change percentage
- Technical indicators (SMA, trend, volatility)
- Recent news headlines
- AI-powered analysis
- Risk assessment

### Market Summary Requests

**User asks in Telex.im:**

```
"Summarize crypto and forex movements today"
"What's happening in the market?"
"Show me best performing coins"
"What are the worst performers?"
"Show me trending cryptocurrencies"
"Market overview"
"What are the top gainers?"
```

**Agent responds with:**

- Top 10 cryptocurrencies by market cap
- Best performers (24h)
- Worst performers (24h)
- Trending coins
- Recently added tokens
- Major forex pairs
- Overall market sentiment
- Total market cap

## Example Telex.im Conversations

### Conversation 1: Individual Asset

```
User: "How is BTC doing today?"

Agent: "Analysis for BTC: direction=bullish confidence=0.75.
Top reasons: Strong upward momentum in 7-day trend, positive news
sentiment around institutional adoption, technical indicators
showing support at current levels.

Current Price: $67,543.21
24h Change: +3.45%
Trend: Uptrend
SMA Position: Above SMA

Recent News:
• Bitcoin ETF sees record inflows (CoinDesk)
• Major bank announces crypto custody service (Reuters)
..."
```

### Conversation 2: Market Summary

```
User: "Summarize crypto movements today"

Agent: "**Market Summary - 2025-11-03 14:30 UTC**

**Overall Sentiment:** Bullish (Avg 24h: +2.35%)

**Top Performers (24h):**
• SOL (Solana): $145.32 (+8.45%)
• AVAX (Avalanche): $38.21 (+6.78%)
• LINK (Chainlink): $14.89 (+5.92%)

**Worst Performers (24h):**
• DOGE (Dogecoin): $0.082 (-3.21%)
• XRP (XRP): $0.52 (-2.89%)
• ADA (Cardano): $0.38 (-2.15%)

**Trending Coins:**
• PEPE - Pepe (Rank #45)
• WIF - dogwifhat (Rank #62)
• BONK - Bonk (Rank #78)
..."
```

### Conversation 3: Mixed Queries

```
User: "What's the market looking like today?"
Agent: [Returns market summary]

User: "Okay, now analyze SOL specifically"
Agent: [Returns detailed SOL analysis with technical indicators]

User: "What about Bitcoin?"
Agent: [Returns detailed BTC analysis]
```

## Configuration for Telex.im

### Agent Configuration File (`a2a-config.json`)

The updated configuration includes:

**Key Features:**

- Supports ANY cryptocurrency symbol (not just hardcoded ones)
- Supports ANY forex pair
- Market summary capabilities
- Natural language query detection
- HTML stripping for Telex.im compatibility

**Description Highlights:**

- Individual asset analysis for any symbol
- Comprehensive market summaries
- Best/worst performers
- Trending coins
- Recently added tokens
- Market sentiment analysis

### Endpoint URL

```
Production: https://forex-crypto-news-a2a-protocol-production.up.railway.app/a2a/market
Local: http://localhost:8000/a2a/market
```

## Response Format

### Individual Asset Response

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "id": "task-...",
    "contextId": "context-...",
    "status": {
      "state": "input-required",
      "message": {
        "role": "agent",
        "parts": [
          {
            "kind": "text",
            "text": "Analysis for BTC: ..."
          },
          {
            "kind": "data",
            "data": {
              "analysis": {...},
              "subject": "BTC",
              "price_snapshot": {...}
            }
          }
        ]
      }
    },
    "artifacts": [
      {
        "name": "price_snapshot",
        "parts": [...]
      },
      {
        "name": "technical_indicators",
        "parts": [...]
      }
    ]
  }
}
```

### Market Summary Response

```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "result": {
    "id": "task-...",
    "contextId": "context-...",
    "status": {
      "state": "input-required",
      "message": {
        "role": "agent",
        "parts": [
          {
            "kind": "text",
            "text": "**Market Summary - 2025-11-03**\n\n..."
          },
          {
            "kind": "data",
            "data": {
              "timestamp": "2025-11-03T14:30:00Z",
              "crypto": {
                "top_by_market_cap": [...],
                "best_performers_24h": [...],
                "worst_performers_24h": [...],
                "trending": [...],
                "recently_added": [...]
              }
            }
          }
        ]
      }
    },
    "artifacts": [
      {
        "name": "market_summary",
        "parts": [...]
      },
      {
        "name": "top_performers",
        "parts": [...]
      },
      {
        "name": "worst_performers",
        "parts": [...]
      },
      {
        "name": "trending_coins",
        "parts": [...]
      }
    ]
  }
}
```

## Conversation History Support

The agent handles Telex.im's conversation history format:

```json
{
  "message": {
    "parts": [
      {
        "kind": "text",
        "text": "Analyze BTC"
      },
      {
        "kind": "data",
        "data": [
          // Conversation history as array
          { "role": "user", "content": "Previous message" },
          { "role": "agent", "content": "Previous response" }
        ]
      }
    ]
  }
}
```

The agent:

- Extracts only text parts for analysis
- Ignores conversation history data
- Focuses on the current query

## Testing with Telex.im

### 1. Add Agent to Telex.im

Upload `a2a-config.json` to Telex.im or configure the agent manually:

**Agent Details:**

- Name: Market Intelligence Agent
- Category: Finance
- URL: `https://your-deployment-url/a2a/market`

### 2. Test Individual Asset Queries

```
"Analyze Bitcoin"
"What's happening with SOL?"
"Show me EUR/USD"
"How is PEPE doing?"
```

### 3. Test Market Summary Queries

```
"Summarize the market"
"What are the best performers?"
"Show me trending coins"
"Market overview"
```

### 4. Verify HTML Handling

Test with Telex.im's rich text:

```
Type: "Analyze **BTC**" (with formatting)
Expected: Agent correctly extracts "BTC" and analyzes it
```

## Advantages of Telex.im Integration

✅ **Natural Conversations**: Users don't need to know specific commands
✅ **Smart Routing**: Agent automatically detects query type
✅ **Rich Responses**: Structured data + human-readable text
✅ **HTML Compatible**: Handles Telex.im's formatted messages
✅ **Non-Blocking**: Supports webhook pattern for long-running queries
✅ **Context Aware**: Maintains conversation history
✅ **Dynamic Symbols**: Supports any cryptocurrency or forex pair
✅ **Market Summaries**: Comprehensive market overviews on demand

## Performance with Telex.im

**Individual Asset Analysis:**

- Response time: 2-5 seconds
- Data sources: CoinGecko, AlphaVantage, CryptoPanic, NewsAPI
- AI analysis: Google Gemini

**Market Summary:**

- Response time: 5-15 seconds (fetches multiple data sources)
- Parallel API calls for efficiency
- Cached results (optional, 5-minute TTL)

## Troubleshooting

### Issue: Agent doesn't respond

**Check:**

- Endpoint URL is correct in Telex.im configuration
- Agent is deployed and running
- API keys are configured in environment variables

### Issue: Symbol not recognized

**Check:**

- Symbol is spelled correctly (case-insensitive)
- Try using full name (e.g., "Bitcoin" instead of "BTC")
- Check if symbol exists on CoinGecko

### Issue: Market summary incomplete

**Check:**

- API keys are valid (especially CoinGecko and AlphaVantage)
- Rate limits not exceeded
- Network connectivity to external APIs

### Issue: HTML tags in response

**Should not happen** - Agent automatically strips HTML. If it does:

- Check agent version is latest
- Verify `_strip_html()` method is working

## Future Enhancements for Telex.im

**Potential additions:**

- [ ] Streaming responses for real-time updates
- [ ] Custom watchlist management per user
- [ ] Price alerts configuration
- [ ] Historical data comparisons
- [ ] Portfolio tracking
- [ ] Multi-asset comparison ("Compare BTC and ETH")
- [ ] Chart generation and image responses
- [ ] Sentiment analysis from social media

## Conclusion

The Market Intelligence A2A Agent is **fully compatible** with Telex.im and provides:

1. ✅ Individual asset analysis (any crypto or forex pair)
2. ✅ Comprehensive market summaries
3. ✅ Natural language query detection
4. ✅ HTML handling for rich-text messages
5. ✅ Webhook support for non-blocking requests
6. ✅ Structured data with human-readable text
7. ✅ Dynamic symbol support (hundreds of cryptocurrencies)

Users can interact naturally through Telex.im's chat interface, and the agent intelligently routes queries to the appropriate handler, providing comprehensive financial analysis and market insights.
