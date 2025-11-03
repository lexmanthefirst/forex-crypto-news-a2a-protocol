# Market Summary Feature

The Market Intelligence A2A Agent now supports comprehensive market summaries that provide an overview of crypto and forex markets, including best/worst performers, trending coins, and newly added tokens.

## Features

### Crypto Market Summary

- **Top Cryptocurrencies**: Top 10 by market cap with current prices
- **Best Performers (24h)**: Top 3 gainers in the last 24 hours
- **Worst Performers (24h)**: Top 3 losers in the last 24 hours
- **Best Performers (7d)**: Top 3 gainers over the past week
- **Worst Performers (7d)**: Top 3 losers over the past week
- **Trending Coins**: Currently trending cryptocurrencies on CoinGecko
- **Recently Added**: Newly listed tokens on CoinGecko
- **Total Market Cap**: Aggregate market cap of top 20 cryptocurrencies
- **Market Sentiment**: Overall sentiment (very bearish, bearish, neutral, bullish, very bullish)

### Forex Summary

- **Major Pairs**: EUR/USD, GBP/USD, USD/JPY with current rates

## Usage

### Trigger Keywords

The agent automatically detects market summary requests when you use keywords like:

- "summarize"
- "summary"
- "overview"
- "what's happening"
- "market update"
- "movements today"
- "market movements"
- "best performing"
- "worst performing"
- "top gainers"
- "top losers"
- "trending"
- "newly added"
- "market snapshot"

### Example Requests

```bash
# General market overview
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
        "parts": [{"kind": "text", "text": "Summarize crypto and forex movements today"}]
      }
    }
  }'

# Best performers
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "role": "user",
        "parts": [{"kind": "text", "text": "What are the best performing coins today?"}]
      }
    }
  }'

# Market overview
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "3",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "role": "user",
        "parts": [{"kind": "text", "text": "What'\''s happening in the market?"}]
      }
    }
  }'

# Trending coins
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "4",
    "method": "message/send",
    "params": {
      "message": {
        "kind": "message",
        "role": "user",
        "parts": [{"kind": "text", "text": "Show me trending cryptocurrencies"}]
      }
    }
  }'
```

## Response Format

The market summary response includes:

### Text Summary

Human-readable formatted text with:

- Overall market sentiment and average 24h change
- Top 3 performers with prices and percentage changes
- Worst 3 performers with prices and percentage changes
- Trending coins with market cap ranks
- Recently added tokens
- Major forex pairs with rates
- Total market cap

### Data Artifacts

**market_summary**: Complete market data including:

```json
{
  "timestamp": "2025-11-03T12:00:00Z",
  "crypto": {
    "top_by_market_cap": [...],
    "best_performers_24h": [...],
    "worst_performers_24h": [...],
    "best_performers_7d": [...],
    "worst_performers_7d": [...],
    "trending": [...],
    "recently_added": [...],
    "total_market_cap_usd": 1500000000000,
    "average_change_24h": 2.5
  },
  "forex": {
    "major_pairs": [...]
  },
  "market_sentiment": "bullish"
}
```

**top_performers**: Array of best performing coins (24h)

**worst_performers**: Array of worst performing coins (24h)

**trending_coins**: Array of trending cryptocurrencies

## Example Response

```
**Market Summary - 2025-11-03 12:00 UTC**

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
• RNDR - Render Token (Rank #34)
• FET - Fetch.ai (Rank #56)

**Recently Added:**
• PYTH - Pyth Network
• JUP - Jupiter
• WEN - Wen

**Major Forex Pairs:**
• EUR/USD: 1.0845
• GBP/USD: 1.2632
• USD/JPY: 149.82

**Total Market Cap (Top 20):** $1,500,234,567,890
```

## Utility Functions

The market summary feature is powered by `utils/market_summary.py`:

### `get_comprehensive_market_summary()`

Fetches all market data in parallel and returns a complete summary object.

### `format_market_summary_text(summary: dict)`

Converts the summary data into human-readable text format.

### `get_top_cryptos_by_market_cap(limit: int)`

Fetches top cryptocurrencies by market cap with 24h and 7d change data.

### `get_trending_cryptos()`

Fetches currently trending cryptocurrencies from CoinGecko.

### `get_recently_added_cryptos(limit: int)`

Fetches newly added tokens to CoinGecko.

### `analyze_performers(cryptos: list)`

Analyzes a list of cryptocurrencies and identifies best/worst performers.

## Testing

Run the test script to verify functionality:

```bash
python test_market_summary.py
```

This will:

1. Fetch top cryptocurrencies by market cap
2. Fetch trending coins
3. Analyze performance metrics
4. Generate a comprehensive market summary
5. Save the full data to `market_summary_sample.json`

## Rate Limits

**CoinGecko Free Tier:**

- 10-30 calls per minute
- Consider adding `COINGECKO_API_KEY` for higher limits

**AlphaVantage Free Tier:**

- 5 calls per minute
- The agent respects rate limits by adding delays between forex requests

## Configuration

No additional configuration is required. The feature uses existing API keys:

- `COINGECKO_API_KEY` (optional, for higher rate limits)
- `ALPHAVANTAGE_API_KEY` (required for forex data)

## Performance Considerations

- Market summary requests fetch data from multiple endpoints
- Response time: 5-15 seconds depending on API response times
- Data is fetched in parallel to minimize latency
- Consider implementing caching for frequently requested summaries

## Future Enhancements

- Cache market summaries with TTL (e.g., 5 minutes)
- Add more forex pairs when rate limits allow
- Include crypto futures and derivatives data
- Add historical comparison (e.g., "up 15% from last week")
- Support custom watchlists for summaries
- Add sector-based analysis (DeFi, Layer 1, Meme coins, etc.)
