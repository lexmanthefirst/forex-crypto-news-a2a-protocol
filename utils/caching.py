"""Redis caching decorator for async functions."""
from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Awaitable, Callable, TypeVar

from utils.redis_client import redis_store

T = TypeVar("T")


def redis_cache(ttl: int = 60) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator to cache async function results in Redis.
    
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
            
            # Try to get from cache
            try:
                cached_result = await redis_store.get_cache(cache_key)
                if cached_result is not None:
                    return cached_result
            except Exception:
                # If cache fails, continue to execute function
                pass
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            try:
                await redis_store.set_cache(cache_key, result, ex=ttl)
            except Exception:
                # If caching fails, still return the result
                pass
            
            return result
        
        return wrapper
    
    return decorator
