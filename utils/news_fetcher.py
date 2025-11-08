from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from utils.caching import redis_cache

logger = logging.getLogger(__name__)

COINGECKO_BASE = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
ALPHAVANTAGE_BASE = os.getenv("ALPHAVANTAGE_BASE", "https://www.alphavantage.co/query")
CRYPTOPANIC_BASE = os.getenv("CRYPTOPANIC_BASE", "https://cryptopanic.com/api/v1")
NEWSAPI_BASE = os.getenv("NEWSAPI_BASE", "https://newsapi.org/v2")

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_API_KEY", "")
CRYPTOPANIC_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")

# Helper map for common coin tickers to their CoinGecko IDs
# Extended to support more cryptocurrencies
COIN_ID_MAP = {
    # Major Cryptocurrencies
    "BTC": "bitcoin",
    "BITCOIN": "bitcoin",
    "ETH": "ethereum",
    "ETHEREUM": "ethereum",
    "XRP": "ripple",
    "RIPPLE": "ripple",
    "LTC": "litecoin",
    "LITECOIN": "litecoin",
    "BCH": "bitcoin-cash",
    "SOL": "solana",
    "SOLANA": "solana",
    "ADA": "cardano",
    "CARDANO": "cardano",
    "DOT": "polkadot",
    "POLKADOT": "polkadot",
    "DOGE": "dogecoin",
    "DOGECOIN": "dogecoin",
    "MATIC": "matic-network",
    "POLYGON": "matic-network",
    "AVAX": "avalanche-2",
    "AVALANCHE": "avalanche-2",
    "LINK": "chainlink",
    "CHAINLINK": "chainlink",
    "UNI": "uniswap",
    "UNISWAP": "uniswap",
    "ATOM": "cosmos",
    "COSMOS": "cosmos",
    "BNB": "binancecoin",
    "BINANCE COIN": "binancecoin",
    "USDT": "tether",
    "TETHER": "tether",
    "USDC": "usd-coin",
    "TRX": "tron",
    "TRON": "tron",
    "TON": "the-open-network",
    "XLM": "stellar",
    "STELLAR": "stellar",
    "SHIB": "shiba-inu",
    "APT": "aptos",
    "APTOS": "aptos",
    "ARB": "arbitrum",
    "ARBITRUM": "arbitrum",
    "OP": "optimism",
    "OPTIMISM": "optimism",
    "INJ": "injective-protocol",
    "INJECTIVE": "injective-protocol",
    "SUI": "sui",
    "NEAR": "near",
    "FET": "fetch-ai",
    "PEPE": "pepe",
    "WIF": "dogwifcoin",
    "BONK": "bonk",
    "FTM": "fantom",
    "FANTOM": "fantom",
    "ALGO": "algorand",
    "ALGORAND": "algorand",
    "VET": "vechain",
    "VECHAIN": "vechain",
    "ICP": "internet-computer",
    "FIL": "filecoin",
    "FILECOIN": "filecoin",
    "HBAR": "hedera-hashgraph",
    "HEDERA": "hedera-hashgraph",
    "APE": "apecoin",
    "APECOIN": "apecoin",
    "SAND": "the-sandbox",
    "SANDBOX": "the-sandbox",
    "MANA": "decentraland",
    "DECENTRALAND": "decentraland",
    "AXS": "axie-infinity",
    "THETA": "theta-token",
    "XTZ": "tezos",
    "TEZOS": "tezos",
    "EOS": "eos",
    "AAVE": "aave",
    "MKR": "maker",
    "MAKER": "maker",
    "GRT": "the-graph",
    "GRAPH": "the-graph",
    "SNX": "synthetix-network-token",
    "SYNTHETIX": "synthetix-network-token",
    "CRV": "curve-dao-token",
    "CURVE": "curve-dao-token",
    "LDO": "lido-dao",
    "LIDO": "lido-dao",
    "QNT": "quant-network",
    "QUANT": "quant-network",
    "STX": "blockstack",
    "STACKS": "blockstack",
    "IMX": "immutable-x",
    "IMMUTABLE": "immutable-x",
    "RUNE": "thorchain",
    "THORCHAIN": "thorchain",
    "KAVA": "kava",
    "ZEC": "zcash",
    "ZCASH": "zcash",
    "DASH": "dash",
    "XMR": "monero",
    "MONERO": "monero",
    "ETC": "ethereum-classic",
}


def _normalize_timestamp(timestamp: str | None) -> str | None:
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def _search_coingecko_id(symbol: str) -> str | None:
    """Search CoinGecko for a coin ID by symbol.
    Returns the coin ID if found, otherwise returns the symbol in lowercase as fallback.
    """
    url = f"{COINGECKO_BASE}/search"
    params = {"query": symbol}
    
    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # Look for exact symbol match in coins
        coins = data.get("coins", [])
        for coin in coins:
            if coin.get("symbol", "").upper() == symbol.upper():
                coin_id = coin.get("id")
                logger.debug(f"[CoinGecko Search] Found ID '{coin_id}' for symbol '{symbol}'")
                return coin_id
        
        # If no exact match, try to use the first result if it's close
        if coins:
            coin_id = coins[0].get("id")
            logger.debug(f"[CoinGecko Search] Using first result '{coin_id}' for symbol '{symbol}'")
            return coin_id
            
    except httpx.HTTPError as exc:
        logger.debug(f"[CoinGecko Search] API failed for '{symbol}': {exc}")
    
    # Fallback to lowercase symbol
    logger.debug(f"[CoinGecko Search] No ID found for '{symbol}', using lowercase as fallback")
    return symbol.lower()


@redis_cache(ttl=60)  # Cache crypto prices for 60 seconds
async def fetch_crypto_prices(symbols: Iterable[str]) -> dict[str, float]:
    symbol_list = [symbol.upper() for symbol in symbols]
    if not symbol_list:
        return {}

    # Get coin IDs - use map first, then search for unknown symbols
    coin_ids = []
    symbol_to_id = {}
    
    for symbol in symbol_list:
        if symbol in COIN_ID_MAP:
            coin_id = COIN_ID_MAP[symbol]
        else:
            # Try to find the coin ID dynamically
            coin_id = await _search_coingecko_id(symbol)
        
        coin_ids.append(coin_id)
        symbol_to_id[symbol] = coin_id
    
    params = {"ids": ",".join(coin_ids), "vs_currencies": "usd"}
    url = f"{COINGECKO_BASE}/simple/price"

    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY

    logger.debug(f"Fetching crypto prices for {symbol_list} from CoinGecko...")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        logger.debug(f"CoinGecko response: {data}")
    except httpx.HTTPError as exc:
        logger.debug(f"CoinGecko API failed: {exc}")
        return {}

    prices: dict[str, float] = {}
    for symbol in symbol_list:
        coin_id = symbol_to_id[symbol]
        usd_price = data.get(coin_id, {}).get("usd")
        if usd_price is not None:
            prices[symbol] = float(usd_price)
    
    logger.debug(f"Parsed prices: {prices}")
    return prices


# Backwards compatibility for prior camelCase export
fetch_Crypto_prices = fetch_crypto_prices


@redis_cache(ttl=60)  # Cache forex rates for 60 seconds
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


@redis_cache(ttl=300)  # Cache crypto news for 5 minutes
async def fetch_crypto_news(limit: int = 3) -> list[dict[str, Any]]:
    """Fetch important crypto news from Cryptopanic."""

    if not CRYPTOPANIC_KEY or limit <= 0:
        return []

    url = f"{CRYPTOPANIC_BASE}/posts/"
    params = {
        "auth_token": CRYPTOPANIC_KEY,
        "kind": "news",
        "filter": "important",
        "public": "true",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
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


@redis_cache(ttl=300)  # Cache forex news for 5 minutes
async def fetch_forex_news(limit: int = 5) -> list[dict[str, Any]]:
    """Fetch forex-related articles from NewsAPI."""

    if not NEWSAPI_KEY or limit <= 0:
        return []

    params = {
        "q": "forex OR currency OR exchange rate OR central bank",
        "apiKey": NEWSAPI_KEY,
        "language": "en",
        "pageSize": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(NEWSAPI_BASE + "/everything", params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
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


@redis_cache(ttl=300)  # Cache combined news for 5 minutes
async def fetch_combined_news(limit: int = 10) -> list[dict[str, Any]]:
    """Return a merged crypto and forex news feed capped to ``limit`` items."""

    if limit <= 0:
        return []

    crypto_limit = max(1, limit // 2)
    forex_limit = limit - crypto_limit


    crypto_news, forex_news = await asyncio.gather(
        fetch_crypto_news(limit=crypto_limit), fetch_forex_news(limit=forex_limit)
    )

    combined = dedupe_news(crypto_news, forex_news)
    return combined[:limit]
