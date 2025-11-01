from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

COINGECKO_BASE = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
ALPHAVANTAGE_BASE = os.getenv("ALPHAVANTAGE_BASE", "https://www.alphavantage.co/query")
CRYPTOPANIC_BASE = os.getenv("CRYPTOPANIC_BASE", "https://cryptopanic.com/api/v1")
NEWSAPI_BASE = os.getenv("NEWSAPI_BASE", "https://newsapi.org/v2")

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_API_KEY", "")
CRYPTOPANIC_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")

# Small helper map for common coin tickers to their CoinGecko IDs
COIN_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "XRP": "ripple",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "SOL": "solana",
}


def _normalize_timestamp(timestamp: str | None) -> str | None:
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def fetch_crypto_prices(symbols: Iterable[str]) -> dict[str, float]:
    symbol_list = [symbol.upper() for symbol in symbols]
    if not symbol_list:
        return {}

    coin_ids = [COIN_ID_MAP.get(symbol, symbol.lower()) for symbol in symbol_list]
    params = {"ids": ",".join(coin_ids), "vs_currencies": "usd"}
    url = f"{COINGECKO_BASE}/simple/price"

    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY

    print(f"DEBUG: Fetching crypto prices for {symbol_list} from CoinGecko...")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        print(f"DEBUG: CoinGecko response: {data}")
    except httpx.HTTPError as exc:
        print(f"DEBUG: CoinGecko API failed: {exc}")
        return {}

    prices: dict[str, float] = {}
    for symbol, coin_id in zip(symbol_list, coin_ids):
        usd_price = data.get(coin_id, {}).get("usd")
        if usd_price is not None:
            prices[symbol] = float(usd_price)
    
    print(f"DEBUG: Parsed prices: {prices}")
    return prices


# Backwards compatibility for prior camelCase export
fetch_Crypto_prices = fetch_crypto_prices


async def fetch_forex_rate(pair: str) -> dict[str, Any]:
    """Return the latest forex rate for a pair formatted like "EUR/USD"."""

    if not ALPHAVANTAGE_KEY:
        raise RuntimeError("AlphaVantage API key not set")
    if "/" not in pair:
        raise ValueError("pair must be in the format BASE/QUOTE, e.g. EUR/USD")

    base, quote = pair.upper().split("/", 1)
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": base,
        "to_currency": quote,
        "apikey": ALPHAVANTAGE_KEY,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(ALPHAVANTAGE_BASE, params=params)
        response.raise_for_status()
        data = response.json()

    rate_info = data.get("Realtime Currency Exchange Rate")
    if not rate_info:
        message = data.get("Error Message") or "Unknown error from AlphaVantage"
        raise RuntimeError(f"Error fetching forex rate: {message}")

    try:
        rate = float(rate_info["5. Exchange Rate"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Invalid rate payload from AlphaVantage") from exc

    timestamp = _normalize_timestamp(rate_info.get("6. Last Refreshed"))
    return {"pair": f"{base}/{quote}", "rate": rate, "timestamp": timestamp}


# Backwards compatibility for legacy misspelling
fetch_forect_rate = fetch_forex_rate


async def fetch_crypto_news(limit: int = 3) -> list[dict[str, Any]]:
    """Fetch important crypto news from Cryptopanic."""

    if not CRYPTOPANIC_KEY or limit <= 0:
        print(f"DEBUG: Crypto news disabled - API_KEY present: {bool(CRYPTOPANIC_KEY)}, limit: {limit}")
        return []

    url = f"{CRYPTOPANIC_BASE}/posts/"
    params = {
        "auth_token": CRYPTOPANIC_KEY,
        "kind": "news",
        "filter": "important",
        "public": "true",
    }

    try:
        print(f"DEBUG: Fetching crypto news from Cryptopanic (limit={limit})...")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        print(f"DEBUG: Cryptopanic returned {len(data.get('results', []))} articles")
    except httpx.HTTPError as exc:
        print(f"DEBUG: Cryptopanic API failed: {exc}")
        return []

    articles: list[dict[str, Any]] = []
    for entry in data.get("results", [])[:limit]:
        articles.append(
            {
                "title": entry.get("title"),
                "url": entry.get("url"),
                "published_at": _normalize_timestamp(entry.get("published_at")),
                "source": entry.get("source", {}).get("title"),
                "symbols": [currency.get("code") for currency in entry.get("currencies", []) if currency],
            }
        )
    return articles


async def fetch_forex_news(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch forex-related articles from NewsAPI."""

    if not NEWSAPI_KEY or limit <= 0:
        print(f"DEBUG: Forex news disabled - API_KEY present: {bool(NEWSAPI_KEY)}, limit: {limit}")
        return []

    params = {
        "q": "forex OR currency OR exchange rate OR central bank",
        "apiKey": NEWSAPI_KEY,
        "language": "en",
        "pageSize": limit,
    }

    try:
        print(f"DEBUG: Fetching forex news from NewsAPI (limit={limit})...")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(NEWSAPI_BASE + "/everything", params=params)
            response.raise_for_status()
            data = response.json()
        print(f"DEBUG: NewsAPI returned {len(data.get('articles', []))} articles")
    except httpx.HTTPError as exc:
        print(f"DEBUG: NewsAPI failed: {exc}")
        return []

    articles: list[dict[str, Any]] = []
    for entry in data.get("articles", [])[:limit]:
        articles.append(
            {
                "title": entry.get("title"),
                "url": entry.get("url"),
                "published_at": _normalize_timestamp(entry.get("publishedAt")),
                "source": entry.get("source", {}).get("name"),
            }
        )
    return articles


def dedupe_news(*news_lists: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for news_list in news_lists:
        for item in news_list:
            key = item.get("url") or item.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
    return deduped


async def fetch_combined_news(limit: int = 10) -> list[dict[str, Any]]:
    """Return a merged crypto and forex news feed capped to ``limit`` items."""

    if limit <= 0:
        return []

    crypto_limit = max(1, limit // 2)
    forex_limit = limit - crypto_limit

    print(f"DEBUG: fetch_combined_news - crypto_limit={crypto_limit}, forex_limit={forex_limit}")

    crypto_news, forex_news = await asyncio.gather(
        fetch_crypto_news(limit=crypto_limit), fetch_forex_news(limit=forex_limit)
    )

    combined = dedupe_news(crypto_news, forex_news)
    print(f"DEBUG: Combined news count after deduplication: {len(combined)}")
    return combined[:limit]