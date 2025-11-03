# Dynamic Symbol Support

The Market Intelligence A2A Agent now supports **any cryptocurrency or forex pair** dynamically, without being limited to a hardcoded list.

## What Changed

### Before

- Limited to 5-6 hardcoded crypto symbols (BTC, ETH, LTC, DOGE, XRP)
- Required code changes to add new cryptocurrencies
- No support for newer tokens

### After

- Supports hundreds of cryptocurrencies automatically
- Dynamic CoinGecko ID lookup for unknown symbols
- Extended base support for 30+ popular cryptocurrencies
- Any forex pair supported via AlphaVantage

## How It Works

### 1. Symbol Extraction

The agent now uses a more flexible regex pattern that matches any 2-5 letter uppercase symbol:

```python
SYMBOL_RE = re.compile(r"\b([A-Z]{2,5})\b")
```

It also maps common cryptocurrency names to their symbols:

- "Bitcoin" → BTC
- "Ethereum" → ETH
- "Solana" → SOL
- "Polygon" → MATIC
- And 20+ more

### 2. CoinGecko ID Resolution

When a symbol is encountered:

1. **Check static map**: First checks if the symbol is in our extended `COIN_ID_MAP` (30+ cryptocurrencies)
2. **Dynamic search**: If not found, uses CoinGecko's search API to find the correct coin ID
3. **Fallback**: If search fails, uses lowercase symbol as fallback

Example flow for "PEPE":

```
User query: "Analyze PEPE"
→ Extract symbol: "PEPE"
→ Not in COIN_ID_MAP
→ Search CoinGecko API for "PEPE"
→ Find coin ID: "pepe"
→ Fetch price and history
→ Generate analysis
```

### 3. Technical Analysis

The `fetch_price_history()` function now:

- Uses the same dynamic lookup mechanism
- Fetches 7-day price history for any valid cryptocurrency
- Falls back gracefully if data is unavailable

### 4. Forex Pairs

Forex pairs work with any valid currency code supported by AlphaVantage:

- Major pairs: EUR/USD, GBP/USD, USD/JPY
- Cross pairs: EUR/GBP, AUD/NZD
- Exotic pairs: USD/TRY, EUR/ZAR

## Supported Cryptocurrencies

### Built-in Fast Support (No API lookup needed)

BTC, ETH, XRP, LTC, BCH, SOL, ADA, DOT, DOGE, MATIC, AVAX, LINK, UNI, ATOM, BNB, USDT, USDC, TRX, TON, XLM, SHIB, APT, ARB, OP, INJ, SUI, NEAR, FET, PEPE, WIF

### Dynamic Support (Automatic lookup)

Any cryptocurrency listed on CoinGecko with a valid symbol

## Example Queries

### Cryptocurrencies

```bash
# Popular coins
"Analyze BTC"
"What's happening with ETH?"
"Show me SOL analysis"

# Meme coins
"Analyze PEPE"
"What about DOGE?"
"Show me SHIB"

# DeFi tokens
"Analyze AAVE"
"What's UNI doing?"
"Show me SUSHI analysis"

# Layer 2s
"Analyze ARB"
"What about OP?"
"Show me MATIC"

# New tokens (will be looked up dynamically)
"Analyze WLD"
"What's RNDR doing?"
"Show me BONK"
```

### Forex Pairs

```bash
"Analyze EUR/USD"
"What's GBP/JPY doing?"
"Show me USD/CHF analysis"
"Analyze AUD/NZD"
```

## Performance Considerations

### API Calls

- Static map lookups: Instant (no API call)
- Dynamic lookups: +1 API call to CoinGecko search endpoint
- Results are cached in the session for repeated queries

### Rate Limits

- CoinGecko free tier: 10-30 calls/minute
- With API key: Higher limits available
- Consider implementing Redis caching for popular symbols

## Future Enhancements

1. **Cache CoinGecko IDs**: Store successful lookups in Redis to avoid repeated searches
2. **Fuzzy Matching**: Handle typos and variations ("Etherium" → "Ethereum")
3. **Multi-Symbol Analysis**: Compare multiple cryptocurrencies in one query
4. **Symbol Validation**: Pre-validate symbols before fetching data
5. **Support More Assets**: Stocks, commodities, bonds via additional data sources

## Testing

Test the dynamic support:

```bash
# Test a built-in symbol
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"kind":"message","role":"user","parts":[{"kind":"text","text":"Analyze SOL"}]}}}'

# Test a symbol requiring lookup
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"kind":"message","role":"user","parts":[{"kind":"text","text":"Analyze AAVE"}]}}}'

# Test by cryptocurrency name
curl -X POST http://localhost:8000/a2a/market \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"kind":"message","role":"user","parts":[{"kind":"text","text":"What about Polygon?"}]}}}'
```

## Troubleshooting

### Symbol Not Found

If a symbol isn't recognized:

1. Check CoinGecko to verify it's listed
2. Try using the full cryptocurrency name
3. Check the debug logs for search results

### API Rate Limits

If you hit rate limits:

1. Add `COINGECKO_API_KEY` to your `.env` file
2. Implement Redis caching for popular symbols
3. Reduce `WATCHLIST` frequency

### Wrong Symbol Matched

If the agent extracts the wrong symbol:

1. Use more specific language ("the BTC price" vs "price")
2. Use the full cryptocurrency name
3. Check if it's matching common English words (filtered in code)
