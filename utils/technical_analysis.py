"""
Simple technical analysis helpers for crypto/forex.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

# coin ID map for common cryptocurrencies
COIN_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "XRP": "ripple",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "SOL": "solana",
    "ADA": "cardano",
    "DOT": "polkadot",
    "DOGE": "dogecoin",
    "MATIC": "matic-network",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "BNB": "binancecoin",
    "USDT": "tether",
    "USDC": "usd-coin",
    "TRX": "tron",
    "TON": "the-open-network",
    "XLM": "stellar",
    "SHIB": "shiba-inu",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "INJ": "injective-protocol",
    "SUI": "sui",
    "NEAR": "near",
    "FET": "fetch-ai",
    "PEPE": "pepe",
    "WIF": "dogwifcoin",
}

COINGECKO_BASE = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")


async def _search_coingecko_id(symbol: str) -> str | None:
    """Search CoinGecko for a coin ID by symbol."""
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
        
        coins = data.get("coins", [])
        for coin in coins:
            if coin.get("symbol", "").upper() == symbol.upper():
                coin_id = coin.get("id")
                return coin_id
        
        if coins:
            coin_id = coins[0].get("id")
            return coin_id
            
    except httpx.HTTPError:
        pass
    
    return symbol.lower()


async def fetch_price_history(symbol: str, days: int = 7) -> list[float]:
    """
    Fetch historical prices for technical analysis.
    Uses CoinGecko market_chart endpoint for crypto.
    Supports any cryptocurrency symbol dynamically.
    """
    symbol_upper = symbol.upper()
    
    # Try to get coin ID from map, otherwise search for it
    if symbol_upper in COIN_ID_MAP:
        coin_id = COIN_ID_MAP[symbol_upper]
    else:
        coin_id = await _search_coingecko_id(symbol_upper)
    
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days)}
    
    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY
    
    print(f"DEBUG: Fetching {days}-day price history for {symbol} (coin_id: {coin_id})...")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # Extract closing prices from [timestamp, price] pairs
        prices = [price for _timestamp, price in data.get("prices", [])]
        print(f"DEBUG: Fetched {len(prices)} price points for {symbol}")
        return prices
    except Exception as exc:
        print(f"DEBUG: Price history fetch failed for {symbol}: {exc}")
        return []


def calculate_indicators(prices: list[float]) -> dict[str, Any]:
    """
    Calculate basic technical indicators.
    """
    if len(prices) < 2:
        return {}
    
    current_price = prices[-1]
    first_price = prices[0]
    
    # Price change
    change_pct = ((current_price - first_price) / first_price) * 100
    
    # Simple moving average
    sma = sum(prices) / len(prices)
    
    # Volatility (standard deviation)
    mean = sma
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    volatility = variance ** 0.5
    
    # Trend direction
    trend = "uptrend" if current_price > sma else "downtrend"
    
    # Support/Resistance levels (simplified)
    support = min(prices)
    resistance = max(prices)
    
    return {
        "current_price": current_price,
        "sma": round(sma, 2),
        "change_pct": round(change_pct, 2),
        "volatility": round(volatility, 2),
        "trend": trend,
        "support": support,
        "resistance": resistance,
        "price_position": "above_sma" if current_price > sma else "below_sma",
    }


async def get_technical_summary(symbol: str) -> dict[str, Any]:
    """
    Get complete technical analysis summary.
    """
    prices = await fetch_price_history(symbol, days=7)
    if not prices:
        return {"error": "Unable to fetch price history"}
    
    indicators = calculate_indicators(prices)
    
    # Generate signal
    signal = "neutral"
    if indicators.get("trend") == "uptrend" and indicators.get("change_pct", 0) > 5:
        signal = "bullish"
    elif indicators.get("trend") == "downtrend" and indicators.get("change_pct", 0) < -5:
        signal = "bearish"
    
    return {
        **indicators,
        "signal": signal,
        "data_points": len(prices),
    }
