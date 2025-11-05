"""Redis caching decorator with in-memory fallback for async functions."""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import time
from typing import Any, Awaitable, Callable, TypeVar

from utils.redis_client import redis_store

T = TypeVar("T")

# In-memory cache as fallback when Redis is unavailable
# Structure: {cache_key: (value, expiry_timestamp)}
_memory_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = asyncio.Lock()


def _cleanup_expired_cache() -> None:
    """Remove expired entries from in-memory cache."""
    current_time = time.time()
    expired_keys = [key for key, (_, expiry) in _memory_cache.items() if expiry < current_time]
    for key in expired_keys:
        _memory_cache.pop(key, None)


async def _get_from_memory_cache(cache_key: str) -> Any | None:
    """Get value from in-memory cache if not expired."""
    async with _cache_lock:
        _cleanup_expired_cache()
        if cache_key in _memory_cache:
            value, expiry = _memory_cache[cache_key]
            if time.time() < expiry:
                return value
            else:
                # Expired, remove it
                _memory_cache.pop(cache_key, None)
    return None


async def _set_to_memory_cache(cache_key: str, value: Any, ttl: int) -> None:
    """Store value in in-memory cache with TTL."""
    async with _cache_lock:
        expiry = time.time() + ttl
        _memory_cache[cache_key] = (value, expiry)
        # Periodically cleanup (when cache size grows)
        if len(_memory_cache) > 100:
            _cleanup_expired_cache()


def redis_cache(ttl: int = 60) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator to cache async function results in Redis with in-memory fallback.
    
    When Redis is unavailable, automatically falls back to in-memory caching
    to maintain performance and reliability. The in-memory cache is cleaned
    up periodically to prevent memory leaks.
    
    Args:
        ttl: Time-to-live in seconds (default: 60)
    
    Usage:
        @redis_cache(ttl=300)
        async def fetch_data(param1, param2):
            # expensive operation
            return result
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Generate cache key from function name and arguments
            key_data = {
                "func": func.__name__,
                "args": args,
                "kwargs": kwargs,
            }
            key_str = json.dumps(key_data, sort_keys=True, default=str)
            cache_key = hashlib.md5(key_str.encode()).hexdigest()
            
            redis_available = False
            
            # Try to get from Redis first
            try:
                cached_result = await redis_store.get_cache(cache_key)
                if cached_result is not None:
                    redis_available = True
                    # Also update memory cache for faster access next time
                    await _set_to_memory_cache(cache_key, cached_result, ttl)
                    return cached_result
                redis_available = True
            except Exception:
                # Redis unavailable, try in-memory cache
                memory_result = await _get_from_memory_cache(cache_key)
                if memory_result is not None:
                    return memory_result
            
            # Execute function if not in cache
            result = await func(*args, **kwargs)
            
            # Store in cache (try both Redis and memory)
            if redis_available:
                try:
                    await redis_store.set_cache(cache_key, result, ex=ttl)
                    # Also store in memory for faster access
                    await _set_to_memory_cache(cache_key, result, ttl)
                except Exception:
                    # If Redis caching fails, at least store in memory
                    await _set_to_memory_cache(cache_key, result, ttl)
            else:
                # Redis not available, use memory cache
                await _set_to_memory_cache(cache_key, result, ttl)
            
            return result
        
        return wrapper
    
    return decorator


def clear_memory_cache() -> None:
    """Clear all in-memory cache (useful for testing)."""
    global _memory_cache
    _memory_cache = {}


def get_memory_cache_stats() -> dict[str, Any]:
    """Get statistics about the in-memory cache."""
    total = len(_memory_cache)
    current_time = time.time()
    expired = sum(1 for _, (_, expiry) in _memory_cache.items() if expiry < current_time)
    active = total - expired
    return {
        "total_entries": total,
        "active_entries": active,
        "expired_entries": expired
    }
