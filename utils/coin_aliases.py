"""
Coin Alias Resolution System

Fetches and caches coin mappings from CoinGecko to enable flexible coin name resolution.
Maps common aliases (BTC, bitcoin, Bitcoin) to standardized CoinGecko IDs.

Example:
    "btc" → "bitcoin"
    "eth" → "ethereum"
    "Bitcoin" → "bitcoin"
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Cache for 1 hour (3600 seconds)
ALIAS_CACHE_TTL = 3600

# Global cache with timestamp
_coin_list_cache: tuple[list[dict[str, Any]], float] | None = None


def fetch_coin_list() -> list[dict[str, Any]]:
    """
    Fetch the complete list of coins from CoinGecko with local caching.
    
    Returns a list of coin dictionaries with:
    - id: CoinGecko ID (e.g., "bitcoin")
    - symbol: Ticker symbol (e.g., "btc")
    - name: Full name (e.g., "Bitcoin")
    
    Cached for 1 hour to avoid excessive API calls.
    
    Returns:
        List of coin dictionaries from CoinGecko API
    """
    global _coin_list_cache
    
    # Check if cache is valid
    if _coin_list_cache is not None:
        coins, cached_at = _coin_list_cache
        if time.time() - cached_at < ALIAS_CACHE_TTL:
            logger.debug(f"Using cached coin list ({len(coins)} coins)")
            return coins
    
    # Fetch fresh data
    try:
        url = "https://api.coingecko.com/api/v3/coins/list"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        coins = response.json()
        logger.info(f"Fetched {len(coins)} coins from CoinGecko")
        
        # Update cache
        _coin_list_cache = (coins, time.time())
        return coins
    except Exception as e:
        logger.error(f"Failed to fetch coin list from CoinGecko: {e}")
        
        # Return cached data even if expired, if available
        if _coin_list_cache is not None:
            logger.warning("Using expired cache due to fetch failure")
            return _coin_list_cache[0]
        
        return []


def build_alias_map() -> dict[str, str]:
    """
    Build a mapping from various coin aliases to CoinGecko IDs.
    
    Creates mappings for:
    - Symbols (lowercase): "btc" → "bitcoin"
    - Symbols (uppercase): "BTC" → "bitcoin"
    - Names (lowercase): "bitcoin" → "bitcoin"
    - Names (original case): "Bitcoin" → "bitcoin"
    - IDs: "bitcoin" → "bitcoin"
    
    Returns:
        Dictionary mapping aliases to CoinGecko IDs
    """
    coins = fetch_coin_list()
    if not coins:
        logger.warning("No coins fetched, returning empty alias map")
        return {}
    
    alias_map: dict[str, str] = {}
    
    for coin in coins:
        coin_id = coin.get("id", "")
        symbol = coin.get("symbol", "")
        name = coin.get("name", "")
        
        if not coin_id:
            continue
        
        # Map ID to itself (for direct lookups)
        alias_map[coin_id] = coin_id
        
        # Map symbol variations
        if symbol:
            alias_map[symbol.lower()] = coin_id
            alias_map[symbol.upper()] = coin_id
        
        # Map name variations
        if name:
            alias_map[name.lower()] = coin_id
            alias_map[name] = coin_id
    
    logger.info(f"Built alias map with {len(alias_map)} mappings")
    return alias_map


# Global cache for alias map (built on first use)
_alias_map_cache: dict[str, str] | None = None


def resolve_coin_alias(query: str) -> str | None:
    """
    Resolve a coin name/symbol/alias to its CoinGecko ID.
    
    Args:
        query: Coin name, symbol, or alias (e.g., "BTC", "bitcoin", "Bitcoin")
    
    Returns:
        CoinGecko ID if found (e.g., "bitcoin"), None otherwise
    
    Examples:
        >>> resolve_coin_alias("BTC")
        "bitcoin"
        >>> resolve_coin_alias("ethereum")
        "ethereum"
        >>> resolve_coin_alias("Solana")
        "solana"
        >>> resolve_coin_alias("unknown")
        None
    """
    global _alias_map_cache
    
    # Build alias map on first use
    if _alias_map_cache is None:
        _alias_map_cache = build_alias_map()
    
    # Try exact match first
    coin_id = _alias_map_cache.get(query)
    if coin_id:
        return coin_id
    
    # Try case-insensitive match
    for alias, cid in _alias_map_cache.items():
        if alias.lower() == query.lower():
            return cid
    
    logger.debug(f"No alias found for: {query}")
    return None


def get_coin_info(coin_id: str) -> dict[str, str] | None:
    """
    Get basic information about a coin by its CoinGecko ID.
    
    Args:
        coin_id: CoinGecko ID (e.g., "bitcoin")
    
    Returns:
        Dictionary with id, symbol, name if found, None otherwise
    """
    coins = fetch_coin_list()
    for coin in coins:
        if coin.get("id") == coin_id:
            return {
                "id": coin.get("id", ""),
                "symbol": coin.get("symbol", ""),
                "name": coin.get("name", "")
            }
    return None


def clear_alias_cache() -> None:
    """Clear the global alias map cache (useful for testing)."""
    global _alias_map_cache
    _alias_map_cache = None
    logger.info("Cleared alias map cache")
