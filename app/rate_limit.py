"""Simple in-memory sliding-window rate limiter.

This is intentionally dependency-free. For multi-replica deployments, replace
this with a Redis-backed limiter (e.g. slowapi + Redis).
"""

import asyncio
import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request

from .config import RATE_LIMIT_CHAT_PER_MINUTE, RATE_LIMIT_SUGGEST_PER_MINUTE

WINDOW_SECONDS = 60.0

_store: Dict[str, Deque[float]] = {}
_lock = asyncio.Lock()


def _rate_limit_key(request: Request, user_id: Optional[int]) -> str:
    """Prefer per-user limits; fall back to the client IP."""
    if user_id is not None:
        return f"user:{user_id}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


async def check_rate_limit(request: Request, user_id: Optional[int], limit: int) -> None:
    """Raise HTTP 429 if the key has exceeded ``limit`` requests in the last minute."""
    if limit <= 0:
        return

    key = _rate_limit_key(request, user_id)
    now = time.monotonic()

    async with _lock:
        timestamps = _store.setdefault(key, deque(maxlen=limit))
        # Evict timestamps outside the sliding window.
        while timestamps and now - timestamps[0] > WINDOW_SECONDS:
            timestamps.popleft()

        if len(timestamps) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Limit: {limit} requests per minute.",
            )

        timestamps.append(now)


async def check_chat_rate_limit(request: Request, user_id: Optional[int]) -> None:
    await check_rate_limit(request, user_id, RATE_LIMIT_CHAT_PER_MINUTE)


async def check_suggest_rate_limit(request: Request, user_id: Optional[int]) -> None:
    await check_rate_limit(request, user_id, RATE_LIMIT_SUGGEST_PER_MINUTE)
