"""
Shared CoinGecko API helper functions.

Provides common functionality for searching and resolving cryptocurrency IDs
to avoid code duplication across modules.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

COINGECKO_BASE = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")


async def search_coin_id(symbol: str) -> str | None:
    """
    Search CoinGecko for a coin ID by symbol.
    
    Returns exact symbol match only (case-insensitive).
    Does NOT fall back to first result to avoid wrong coin matches.
    
    Args:
        symbol: Coin symbol (e.g., "BTC", "ETH", "DOGE")
    
    Returns:
        CoinGecko ID if exact match found, None otherwise
    
    Examples:
        >>> await search_coin_id("BTC")
        "bitcoin"
        >>> await search_coin_id("INVALIDCOIN")
        None
    """
    url = f"{COINGECKO_BASE}/search"
    params = {"query": symbol}
    
    headers = {"Accept": "application/json"}
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            
            if response.status_code == 429:
                logger.warning(f"[CoinGecko Search] Rate limited for symbol: {symbol}")
                return None
            
            response.raise_for_status()
            data = response.json()
        
        coins = data.get("coins", [])
        
        for coin in coins:
            if coin.get("symbol", "").upper() == symbol.upper():
                coin_id = coin.get("id")
                logger.debug(f"[CoinGecko Search] Found exact match: {symbol} → {coin_id}")
                return coin_id
        
        logger.debug(f"[CoinGecko Search] No exact match for symbol: {symbol}")
        return None
            
    except httpx.HTTPError as e:
        logger.warning(f"[CoinGecko Search] HTTP error for {symbol}: {e}")
        return None
    except Exception as e:
        logger.error(f"[CoinGecko Search] Unexpected error for {symbol}: {e}")
        return None
