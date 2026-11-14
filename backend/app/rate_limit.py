from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from redis import Redis

from .config import get_settings
from .errors import APIError


def get_rate_limit_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


RateLimitRedis = Annotated[Redis, Depends(get_rate_limit_redis)]


def rate_limit(*, auth: bool = False) -> Callable:
    def dependency(request: Request, redis: RateLimitRedis) -> None:
        settings = get_settings()
        limit = settings.auth_rate_limit if auth else settings.api_rate_limit
        window = settings.rate_limit_window_seconds
        client = request.client.host if request.client else "unknown"
        route = request.url.path
        bucket = int(time.time()) // window
        scope = "auth" if auth else "api"
        identity = hashlib.sha256(f"{scope}:{client}:{route}".encode()).hexdigest()
        key = f"chainguard:rate:{scope}:{identity}:{bucket}"
        try:
            count = redis.incr(key)
            if count == 1:
                redis.expire(key, window + 1)
        except Exception as exc:
            if auth:
                raise APIError(
                    503,
                    "rate_limit_unavailable",
                    "authentication service is temporarily unavailable",
                ) from exc
            return
        if count > limit:
            raise APIError(
                429,
                "rate_limited",
                "request rate limit exceeded",
                details={"retry_after_seconds": window},
                headers={"Retry-After": str(window)},
            )

    return dependency
