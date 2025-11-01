"""
Simple technical analysis helpers for crypto/forex.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx


async def fetch_price_history(symbol: str, days: int = 7) -> list[float]:
    """
    Fetch historical prices for technical analysis.
    Uses CoinGecko market_chart endpoint for crypto.
    """
    coin_id_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "XRP": "ripple",
        "LTC": "litecoin",
    }
    
    coin_id = coin_id_map.get(symbol.upper(), symbol.lower())
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days)}
    
    print(f"DEBUG: Fetching {days}-day price history for {symbol} from CoinGecko...")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
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
