"""
Session History Management for A2A Protocol

Manages conversation history using Redis with automatic TTL and FIFO limit.
Provides session-based context for multi-turn conversations.

Features:
- Redis-based storage with 24-hour TTL
- Configurable message limit per session (default: 50)
- FIFO eviction when limit exceeded
- Automatic cleanup of expired sessions
- Graceful degradation when Redis unavailable
"""
from __future__ import annotations

import logging
from typing import Any

from models.a2a import A2AMessage
from utils.redis_client import redis_store

logger = logging.getLogger(__name__)

# Session TTL: 24 hours (86400 seconds)
SESSION_TTL = 86400

# Maximum messages per session (FIFO)
MAX_MESSAGES_PER_SESSION = 50


class SessionStore:
    """Manages conversation history for A2A sessions."""
    
    def __init__(self, max_messages: int = MAX_MESSAGES_PER_SESSION, ttl: int = SESSION_TTL):
        """
        Initialize session store.
        
        Args:
            max_messages: Maximum messages to keep per session (FIFO)
            ttl: Session time-to-live in seconds (default: 24 hours)
        """
        self.max_messages = max_messages
        self.ttl = ttl
        self._memory_fallback: dict[str, list[dict[str, Any]]] = {}
    
    def _get_session_key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"session:history:{session_id}"
    
    async def append_message(self, session_id: str, message: A2AMessage) -> None:
        """
        Append a message to session history.
        
        Automatically enforces FIFO limit and refreshes TTL.
        
        Args:
            session_id: Unique session identifier
            message: A2A message to append
        """
        import json
        
        key = self._get_session_key(session_id)
        message_dict = message.model_dump(mode='json', exclude_none=True)
        
        try:
            # Get current history
            history = await self.get_history(session_id)
            
            # Append new message
            history.append(message_dict)
            
            # Enforce FIFO limit
            if len(history) > self.max_messages:
                history = history[-self.max_messages:]
            
            # Store entire history as JSON string
            await redis_store.client.set(key, json.dumps(history, default=str), ex=self.ttl)
            
            logger.debug(f"Appended message to session {session_id} ({len(history)} total)")
            
        except Exception as e:
            logger.warning(f"Failed to append message to Redis session {session_id}: {e}")
            # Fallback to memory
            if session_id not in self._memory_fallback:
                self._memory_fallback[session_id] = []
            self._memory_fallback[session_id].append(message_dict)
            if len(self._memory_fallback[session_id]) > self.max_messages:
                self._memory_fallback[session_id] = self._memory_fallback[session_id][-self.max_messages:]
    
    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """
        Retrieve conversation history for a session.
        
        Args:
            session_id: Unique session identifier
        
        Returns:
            List of message dictionaries (oldest first)
        """
        import json
        
        key = self._get_session_key(session_id)
        
        try:
            # Get history JSON from Redis
            raw = await redis_store.client.get(key)
            if raw:
                history = json.loads(raw)
                logger.debug(f"Retrieved {len(history)} messages from session {session_id}")
                return history
            return []
            
        except Exception as e:
            logger.warning(f"Failed to get history from Redis for session {session_id}: {e}")
            # Fallback to memory
            return self._memory_fallback.get(session_id, [])
    
    async def clear_history(self, session_id: str) -> None:
        """
        Clear conversation history for a session.
        
        Args:
            session_id: Unique session identifier
        """
        key = self._get_session_key(session_id)
        
        try:
            await redis_store.client.delete(key)
            logger.info(f"Cleared history for session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to clear Redis history for session {session_id}: {e}")
        
        # Also clear memory fallback
        self._memory_fallback.pop(session_id, None)
    
    async def get_session_count(self) -> int:
        """
        Get the number of active sessions.
        
        Returns:
            Number of sessions in Redis
        """
        try:
            pattern = self._get_session_key("*")
            keys = await redis_store.client.keys(pattern)
            return len(keys)
        except Exception as e:
            logger.warning(f"Failed to get session count: {e}")
            return len(self._memory_fallback)
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Manually trigger cleanup of expired sessions.
        
        Note: Redis automatically handles TTL expiration, but this
        can be used to explicitly clean up if needed.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            pattern = self._get_session_key("*")
            keys = await redis_store.client.keys(pattern)
            
            cleaned = 0
            for key in keys:
                ttl = await redis_store.client.ttl(key)
                if ttl == -2:  # Key doesn't exist
                    cleaned += 1
                elif ttl == -1:  # Key exists but has no TTL
                    # Set TTL for orphaned keys
                    await redis_store.client.expire(key, self.ttl)
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} expired sessions")
            
            return cleaned
            
        except Exception as e:
            logger.warning(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    def get_memory_stats(self) -> dict[str, Any]:
        """
        Get statistics about in-memory fallback cache.
        
        Returns:
            Dictionary with cache statistics
        """
        total_messages = sum(len(msgs) for msgs in self._memory_fallback.values())
        return {
            "sessions": len(self._memory_fallback),
            "total_messages": total_messages,
            "avg_messages_per_session": total_messages / len(self._memory_fallback) if self._memory_fallback else 0
        }


# Global session store instance
session_store = SessionStore()
