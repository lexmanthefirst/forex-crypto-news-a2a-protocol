# Building a Market Intelligence Agent with A2A Protocol: AI-Powered Crypto & Forex Analysis

As financial markets become increasingly complex, traders and developers need intelligent systems that can process vast amounts of data and provide actionable insights in real-time. In this article, I'll walk you through how I built a Market Intelligence Agent using the Agent-to-Agent (A2A) protocol, combining AI analysis, technical indicators, and multi-source news aggregation.

## What is the A2A Protocol?

The Agent-to-Agent (A2A) protocol is a standardized communication framework that enables AI agents to interact with each other seamlessly. Think of it as a universal language for AI systems. By implementing A2A, our market intelligence agent can integrate with platforms like Telex.im and communicate with other agents in the ecosystem.

## The Problem

Traditional market analysis tools often require users to:

- Navigate complex interfaces
- Learn specific query languages
- Manually aggregate data from multiple sources
- Interpret raw technical indicators without context

I wanted to create something different: an agent that understands natural language, aggregates multiple data sources automatically, and provides AI-powered insights that combine technical analysis with market sentiment.

## Architecture Overview

The system is built on a modern Python stack with the following components:

### Core Technologies

- **FastAPI**: High-performance web framework for the JSON-RPC 2.0 API
- **Google Gemini**: AI model for generating market analysis and insights
- **Redis**: Session storage and caching layer
- **APScheduler**: Background job scheduling for watchlist monitoring

### Data Sources

- **CoinGecko**: Real-time cryptocurrency prices
- **AlphaVantage**: Forex exchange rates
- **CryptoPanic**: Crypto-specific news aggregation
- **NewsAPI**: General market news

## Key Features

### 1. Natural Language Processing

Users can ask questions in plain English:

```
"Analyze BTC"
"What's the outlook for EUR/USD?"
"Give me a technical analysis of ETH"
```

The agent parses these queries, extracts relevant symbols or currency pairs, and orchestrates a complete analysis pipeline.

### 2. Technical Analysis

The system fetches 7-day price history and calculates:

- Simple Moving Averages (SMA)
- Price volatility
- Support and resistance levels
- Trend direction and strength

These indicators provide quantitative context for the AI's qualitative analysis.

### 3. AI-Powered Insights

Google Gemini processes the technical data, recent news, and market context to generate:

- Market sentiment analysis
- Confidence scores
- Reasoning for predictions
- Risk assessments
- Actionable recommendations

### 4. Multi-Source News Aggregation

The agent pulls relevant news from multiple sources, filters by symbol or currency pair, and includes only the most pertinent headlines in the analysis. This prevents information overload while ensuring comprehensive coverage.

### 5. Webhook Notifications

For automated trading systems or monitoring applications, the agent supports webhook notifications with:

- Configurable cooldown periods
- Impact threshold filtering
- Bearer token authentication
- Both blocking and non-blocking response patterns

## Implementation Deep Dive

### The Message Processing Pipeline

When a request arrives, the agent follows this pipeline:

1. **Request Validation**: JSON-RPC 2.0 structure validation using Pydantic models
2. **Symbol Extraction**: Regex-based parsing to identify crypto symbols or forex pairs
3. **Data Collection**: Parallel API calls to price and news sources
4. **Technical Analysis**: Indicator calculation from historical data
5. **AI Analysis**: Gemini processes all collected data with structured prompting
6. **Response Formatting**: Results packaged as A2A protocol artifacts

### Handling HTML in Rich Text Messages

One challenge with platform integration was handling HTML-formatted messages from Telex.im. The solution was a preprocessing step that strips HTML tags and decodes entities before symbol extraction:

```python
def _strip_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = ' '.join(text.split())
    return text
```

### Non-Blocking Webhook Responses

For platform integrations requiring asynchronous responses, the agent implements a non-blocking pattern:

1. Receive request with webhook configuration
2. Immediately return acknowledgment
3. Process analysis in background task
4. POST results to webhook URL with authentication

This ensures the client doesn't time out while waiting for complex analysis operations.

### Scheduled Watchlist Monitoring

The agent includes a background scheduler that periodically analyzes configured symbols:

```python
scheduler.add_job(_scheduled_analysis_job, "interval", minutes=poll_minutes)
```

This enables proactive monitoring and alerting without manual intervention.

## Deployment Strategy

The project is containerized with Docker and includes:

- **Dockerfile**: Python 3.13-slim base with optimized layer caching
- **docker-compose.yml**: Single-service deployment with external Redis
- **GitHub Actions**: Automated builds and publishing to GitHub Container Registry

This makes deployment to any cloud platform straightforward - from simple VPS hosting to Kubernetes clusters.

## Challenges and Solutions

### Challenge 1: Rate Limiting

**Problem**: Multiple API sources with different rate limits.
**Solution**: Implemented configurable fetch limits and Redis caching for repeated queries.

### Challenge 2: Gemini API Integration

**Problem**: Initial implementation used incorrect API method calls.
**Solution**: Updated to use `client.models.generate_content()` with proper error handling.

### Challenge 3: Context Preservation

**Problem**: Maintaining conversation context across requests.
**Solution**: Redis-based session storage with context IDs and message history.

### Challenge 4: Data Format Flexibility

**Problem**: Telex.im sends conversation history as lists, not dictionaries.
**Solution**: Updated Pydantic models to accept `dict | list` for the data field.

## Real-World Usage Example

Here's a complete interaction flow:

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "role": "user",
      "parts": [{ "kind": "text", "text": "Analyze BTC" }]
    }
  }
}
```

**Response includes:**

- AI-generated analysis with sentiment and confidence
- Technical indicators (SMA, volatility, trends)
- Recent news headlines
- Current price data
- Historical context

The agent might respond: "Analysis for BTC: direction=bullish confidence=0.75. Top reasons: Strong upward momentum in 7-day trend, positive news sentiment around institutional adoption, technical indicators showing support at current levels."

## Performance Considerations

The system is designed for production use with:

- Async/await throughout for concurrent operations
- Connection pooling for external APIs
- Redis caching to reduce redundant API calls
- Structured logging for debugging and monitoring
- Error handling with proper JSON-RPC error codes

## Future Enhancements

Potential areas for expansion:

1. **More Asset Classes**: Stocks, commodities, bonds
2. **Advanced Technical Analysis**: RSI, MACD, Fibonacci retracements
3. **Backtesting**: Historical performance validation
4. **Multi-Agent Collaboration**: Coordinate with other A2A agents
5. **Custom Indicators**: User-defined technical calculations
6. **Sentiment Analysis**: Deep learning on news content
7. **Portfolio Management**: Track and analyze multiple positions

## Lessons Learned

Building this agent taught me several valuable lessons:

1. **Protocol Standards Matter**: A2A's standardization makes integration significantly easier
2. **Flexibility is Key**: Supporting multiple request/response patterns increases adoption
3. **Error Handling is Critical**: Financial data requires robust error handling and validation
4. **Modular Architecture**: Separating concerns makes testing and maintenance simpler
5. **Documentation Saves Time**: Clear API examples reduce integration friction

## Getting Started

The project is open source and available on GitHub:
https://github.com/lexmanthefirst/forex-crypto-news-a2a-protocol

To run it yourself:

1. Clone the repository
2. Set up API keys in `.env`
3. Run with Docker: `docker-compose up -d`
4. Start querying: `POST http://localhost:8000/a2a/market`

## Conclusion

Building a market intelligence agent with the A2A protocol demonstrates how standardized communication frameworks can enable powerful AI integrations. By combining real-time data, technical analysis, and AI insights, we can create tools that make financial market analysis more accessible and actionable.

The modular architecture means you can adapt this for your specific needs - whether that's adding new data sources, implementing custom analysis algorithms, or integrating with your trading platform.

What would you build with an A2A-enabled market intelligence agent? The possibilities are vast, and I'm excited to see how the community extends this foundation.

---

Built as part of the HNG Internship program. Check out more at https://hng.tech

If you found this article helpful, please consider giving the repository a star on GitHub and sharing your own A2A agent implementations!

**Tags:** #AI #Crypto #Forex #AgentToAgent #A2A #Python #FastAPI #TradingBots #FinTech #MachineLearning
