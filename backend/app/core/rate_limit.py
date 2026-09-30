"""Sliding-window rate limiter: in-memory (single process). Redis-backed variant if REDIS_URL is set."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

_hits: dict = defaultdict(deque)


async def check_rate_limit(request: Request, key_prefix: str, limit: int = 10, window_seconds: int = 60) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{key_prefix}:{ip}"
    now = time.time()
    if settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds + 5)
            *_, count, _ = await pipe.execute()
            if count > limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded. Try again shortly.")
            return
        except HTTPException:
            raise
        except Exception:
            pass  # fall through to in-memory
    q = _hits[key]
    while q and q[0] <= now - window_seconds:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded. Try again shortly.")
    q.append(now)
