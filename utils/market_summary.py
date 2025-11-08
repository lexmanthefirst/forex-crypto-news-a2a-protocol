"""
Market summary utilities for crypto and forex overview.
Provides best/worst performers, newly added coins, and market trends.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

COINGECKO_BASE = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
ALPHAVANTAGE_BASE = os.getenv("ALPHAVANTAGE_BASE", "https://www.alphavantage.co/query")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")


async def get_top_cryptos_by_market_cap(limit: int = 10) -> list[dict[str, Any]]:
    """
    Fetch top cryptocurrencies by market cap with price change data.
    """
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    }
    
    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        return data
    except Exception:
        return []


async def get_trending_cryptos() -> list[dict[str, Any]]:
    """
    Fetch trending/newly popular cryptocurrencies.
    """
    url = f"{COINGECKO_BASE}/search/trending"
    
    headers = {"Accept": "application/json"}
    params = {}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # Extract coin info from trending data
        trending = []
        for item in data.get("coins", [])[:7]:
            coin_data = item.get("item", {})
            trending.append({
                "id": coin_data.get("id"),
                "symbol": coin_data.get("symbol", "").upper(),
                "name": coin_data.get("name"),
                "market_cap_rank": coin_data.get("market_cap_rank"),
                "price_btc": coin_data.get("price_btc"),
            })
        
        return trending
    except Exception:
        return []


async def get_recently_added_cryptos(limit: int = 5) -> list[dict[str, Any]]:
    """
    Fetch recently added cryptocurrencies to CoinGecko.
    """
    url = f"{COINGECKO_BASE}/coins/list/new"
    
    headers = {"Accept": "application/json"}
    params = {}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        
        # Return limited results
        recently_added = data[:limit] if isinstance(data, list) else []
        return recently_added
    except Exception:
        return []


async def get_forex_majors_summary() -> list[dict[str, Any]]:
    """
    Fetch summary of major forex pairs (limited by AlphaVantage free tier).
    Returns basic info for major pairs.
    """
    major_pairs = ["EUR/USD", "GBP/USD", "USD/JPY"]
    
    if not ALPHAVANTAGE_KEY:
        print("DEBUG: AlphaVantage API key not configured")
        return []
    
    results = []
    for pair in major_pairs:
        try:
            base, quote = pair.split("/")
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
            
            rate_info = data.get("Realtime Currency Exchange Rate", {})
            if rate_info:
                results.append({
                    "pair": pair,
                    "rate": float(rate_info.get("5. Exchange Rate", 0)),
                    "timestamp": rate_info.get("6. Last Refreshed"),
                })
            
            # Respect rate limits (5 calls/min for free tier)
            await asyncio.sleep(12)
            
        except Exception:
            continue
    
    return results


def analyze_performers(cryptos: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Analyze crypto performance and identify best/worst performers.
    """
    if not cryptos:
        return {
            "best_24h": [],
            "worst_24h": [],
            "best_7d": [],
            "worst_7d": [],
            "total_market_cap": 0,
            "average_change_24h": 0,
        }
    
    # Sort by 24h change
    valid_24h = [c for c in cryptos if c.get("price_change_percentage_24h") is not None]
    sorted_24h = sorted(valid_24h, key=lambda x: x.get("price_change_percentage_24h", 0), reverse=True)
    
    # Sort by 7d change
    valid_7d = [c for c in cryptos if c.get("price_change_percentage_7d_in_currency") is not None]
    sorted_7d = sorted(valid_7d, key=lambda x: x.get("price_change_percentage_7d_in_currency", 0), reverse=True)
    
    # Calculate total market cap
    total_market_cap = sum(c.get("market_cap", 0) for c in cryptos)
    
    # Calculate average 24h change
    if valid_24h:
        average_change_24h = sum(c.get("price_change_percentage_24h", 0) for c in valid_24h) / len(valid_24h)
    else:
        average_change_24h = 0
    
    return {
        "best_24h": sorted_24h[:3],
        "worst_24h": sorted_24h[-3:] if len(sorted_24h) > 3 else [],
        "best_7d": sorted_7d[:3],
        "worst_7d": sorted_7d[-3:] if len(sorted_7d) > 3 else [],
        "total_market_cap": total_market_cap,
        "average_change_24h": average_change_24h,
    }


async def get_comprehensive_market_summary() -> dict[str, Any]:
    """
    Get a comprehensive market summary including:
    - Top cryptos by market cap
    - Best/worst performers
    - Trending coins
    - Recently added coins
    - Major forex pairs
    """
    results = await asyncio.gather(
        get_top_cryptos_by_market_cap(limit=20),
        get_trending_cryptos(),
        get_recently_added_cryptos(limit=5),
        get_forex_majors_summary(),
        return_exceptions=True
    )
    
    top_cryptos = results[0] if isinstance(results[0], list) else []
    trending = results[1] if isinstance(results[1], list) else []
    recently_added = results[2] if isinstance(results[2], list) else []
    forex_majors = results[3] if isinstance(results[3], list) else []
    
    # Analyze performance
    performance = analyze_performers(top_cryptos)
    
    # Build summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "crypto": {
            "top_by_market_cap": top_cryptos[:10],
            "best_performers_24h": performance["best_24h"],
            "worst_performers_24h": performance["worst_24h"],
            "best_performers_7d": performance["best_7d"],
            "worst_performers_7d": performance["worst_7d"],
            "trending": trending,
            "recently_added": recently_added,
            "total_market_cap_usd": performance["total_market_cap"],
            "average_change_24h": performance["average_change_24h"],
        },
        "forex": {
            "major_pairs": forex_majors,
        },
        "market_sentiment": _determine_market_sentiment(performance["average_change_24h"]),
    }
    
    return summary


def _determine_market_sentiment(average_change: float) -> str:
    """Determine overall market sentiment based on average change."""
    if average_change > 5:
        return "very_bullish"
    elif average_change > 2:
        return "bullish"
    elif average_change > -2:
        return "neutral"
    elif average_change > -5:
        return "bearish"
    else:
        return "very_bearish"


def format_market_summary_text(summary: dict[str, Any]) -> str:
    """
    Format market summary into human-readable text.
    """
    crypto = summary.get("crypto", {})
    forex = summary.get("forex", {})
    
    text = f"**Market Summary - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}**\n\n"
    
    # Market sentiment
    sentiment = summary.get("market_sentiment", "neutral").replace("_", " ").title()
    avg_change = crypto.get("average_change_24h", 0)
    text += f"**Overall Sentiment:** {sentiment} (Avg 24h: {avg_change:+.2f}%)\n\n"
    
    # Best performers 24h
    text += "**Top Performers (24h):**\n"
    for coin in crypto.get("best_performers_24h", [])[:3]:
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        change = coin.get("price_change_percentage_24h", 0)
        price = coin.get("current_price", 0)
        text += f"• {symbol} ({name}): ${price:,.2f} ({change:+.2f}%)\n"
    
    # Worst performers 24h
    text += "\n**Worst Performers (24h):**\n"
    for coin in crypto.get("worst_performers_24h", [])[:3]:
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        change = coin.get("price_change_percentage_24h", 0)
        price = coin.get("current_price", 0)
        text += f"• {symbol} ({name}): ${price:,.2f} ({change:+.2f}%)\n"
    
    # Trending coins
    text += "\n**Trending Coins:**\n"
    for coin in crypto.get("trending", [])[:5]:
        symbol = coin.get("symbol", "")
        name = coin.get("name", "")
        rank = coin.get("market_cap_rank", "N/A")
        text += f"• {symbol} - {name} (Rank #{rank})\n"
    
    # Recently added
    recently_added = crypto.get("recently_added", [])
    if recently_added:
        text += "\n**Recently Added:**\n"
        for coin in recently_added[:3]:
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            text += f"• {symbol} - {name}\n"
    
    # Forex majors
    forex_pairs = forex.get("major_pairs", [])
    if forex_pairs:
        text += "\n**Major Forex Pairs:**\n"
        for pair_data in forex_pairs:
            pair = pair_data.get("pair", "")
            rate = pair_data.get("rate", 0)
            text += f"• {pair}: {rate:.4f}\n"
    
    # Total market cap
    total_cap = crypto.get("total_market_cap_usd", 0)
    if total_cap > 0:
        text += f"\n**Total Market Cap (Top 20):** ${total_cap:,.0f}"
    
    return text
