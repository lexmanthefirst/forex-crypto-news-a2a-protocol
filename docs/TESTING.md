# Testing Guide

This document outlines recommended practices for validating the **a2a-news-tracker** codebase. It covers automated tests, end-to-end checks, and manual verification steps. Adapt these workflows to match your local tooling and CI environment.

---

## 1. Environment Preparation

1. Copy `.env.example` to `.env` (or create one) and populate required keys:
   - `REDIS_URL`
   - `COINGECKO_API_KEY` (optional demo key)
   - `ALPHAVANTAGE_API_KEY`
   - `NEWSAPI_API_KEY`
   - `CRYPTOPANIC_API_KEY`
2. Install dependencies: `pip install -e .`
3. Ensure Redis is reachable (local instance or remote service).

---

## 2. Automated Tests

At the moment the project does not ship with an explicit unit-test suite. To add automated coverage:

1. Create a `tests/` package with fixtures for FastAPI, Redis, and HTTP mocks (e.g., using `pytest`, `pytest-asyncio`, `respx`).
2. Suggested test modules:
   - `test_news_fetcher.py`: mock external APIs and validate parsing, timestamp normalization, and deduplication.
   - `test_gemini_client.py`: patch Gemini responses and ensure fallback logic creates valid `TaskResult` objects.
   - `test_redis_client.py`: use `fakeredis` or a containerized Redis to exercise session and task helpers.
   - `test_market_agent.py`: validate end-to-end message processing with mocked fetchers/notifiers.
   - `test_main.py`: drive FastAPI routes via `httpx.AsyncClient` or `fastapi.testclient`.
3. Run the suite:
   ```bash
   pytest
   ```

_Note:_ When writing asynchronous tests, decorate with `@pytest.mark.asyncio` and use `pytest-asyncio>=0.21` or similar.

---

## 3. Manual Smoke Tests

After starting the API (`uvicorn main:app --reload`):

1. **Health Check**

   ```bash
   curl http://localhost:8000/health
   ```

   Expect `{ "status": "healthy" }` with Redis marked `ok`.

2. **JSON-RPC message/send**

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

   Verify that the response contains a `TaskResult` with artifacts and status.

3. **JSON-RPC execute**

   ```bash
   curl -X POST http://localhost:8000/a2a/market \
     -H "Content-Type: application/json" \
     -d '{
           "jsonrpc": "2.0",
           "id": "2",
           "method": "execute",
           "params": {
             "contextId": "demo-context",
             "taskId": "demo-task",
             "messages": [
               {
                 "kind": "message",
                 "role": "user",
                 "parts": [{"kind": "text", "text": "Analyze EUR/USD"}]
               }
             ]
           }
         }'
   ```

4. **Notification Check**

   - Temporarily lower `ANALYSIS_IMPACT_THRESHOLD` and `NOTIFICATION_COOLDOWN_SECONDS` in `.env`.
   - Confirm console logging or webhook payloads are triggered for high-impact analyses.

5. **Scheduler Run**
   - Set `POLL_INTERVAL_MINUTES=1` for local testing.
   - Watch logs to ensure `_scheduled_analysis_job` executes and processes watchlist entries without raising exceptions.

---

## 4. Integration Considerations

- **External APIs**: When running tests in CI, mock external HTTP calls (CoinGecko, AlphaVantage, NewsAPI, Cryptopanic, Gemini) to avoid rate limits and ensure deterministic results.
- **Redis**: For automated pipelines use a disposable Redis container or `fakeredis` for unit tests.
- **Gemini Client**: If the Gemini API is unavailable, verify the rule-based fallback still produces valid responses.

---

## 5. Continuous Integration Tips

1. Add `pytest` and `ruff` (or `flake8`) runs to your CI pipeline.
2. Cache dependencies using the virtual environment or `.venv` path.
3. Surface coverage reports (e.g., `pytest --cov=.`) to track analytics over time.
4. Fail fast on formatting or lint issues before hitting runtime tests.

---

## 6. Troubleshooting

- **Missing API Keys**: The agent raises descriptive errors when required keys are absent. Double-check your `.env` and environment variables.
- **Redis Connection Errors**: Ensure the `REDIS_URL` host is reachable; use `redis-cli ping` or the project’s `/health` endpoint to verify.
- **Timeouts**: External services default to 10s timeouts. Adjust locally by patching or configuring `httpx.AsyncClient` instances as needed.

---

By following these guidelines you can confidently validate changes before deploying them to staging or production environments.
