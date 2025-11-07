from __future__ import annotations

import json
import os
from typing import Any

import redis.asyncio as aioredis

from models.a2a import TaskResult

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


class RedisClient:
    def __init__(self, url: str = REDIS_URL):
        self._url = url
        self._client: aioredis.Redis | None = None

    async def initialize(self) -> None:
        if self._client is None:
            self._client = aioredis.from_url(self._url, encoding="utf-8", decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client is not initialized. Call initialize() first.")
        return self._client

    # Session helpers
    async def set_session(self, session_id: str, payload: dict[str, Any], ex: int = 3600) -> None:
        await self.client.set(f"session:{session_id}", json.dumps(payload), ex=ex)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        raw = await self.client.get(f"session:{session_id}")
        return json.loads(raw) if raw else None

    # Store last analysis for a pair/subject
    async def set_latest_analysis(self, key: str, payload: dict[str, Any], ex: int = 3600) -> None:
        await self.client.set(f"analysis:{key}", json.dumps(payload), ex=ex)

    async def get_latest_analysis(self, key: str) -> dict[str, Any] | None:
        raw = await self.client.get(f"analysis:{key}")
        return json.loads(raw) if raw else None

    # Task helpers
    async def set_task(self, task: TaskResult, ex: int | None = 3600) -> None:
        await self.client.set(f"tasks:{task.taskId}", task.model_dump_json(), ex=ex)

    async def get_task(self, task_id: str) -> TaskResult | None:
        raw = await self.client.get(f"tasks:{task_id}")
        if not raw:
            return None
        try:
            return TaskResult.model_validate_json(raw)
        except ValueError as exc:
            raise RuntimeError(f"Stored task payload for {task_id} is invalid") from exc

    # Generic cache helpers
    async def get_cache(self, key: str) -> Any | None:
        """Get cached value by key."""
        raw = await self.client.get(f"cache:{key}")
        return json.loads(raw) if raw else None

    async def set_cache(self, key: str, value: Any, ex: int = 60) -> None:
        """Set cached value with expiration time in seconds."""
        await self.client.set(f"cache:{key}", json.dumps(value, default=str), ex=ex)


redis_store = RedisClient()

