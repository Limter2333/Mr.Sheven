"""Rate limiter: 10 requests per minute per IP.

Uses Redis INCR with TTL for distributed counting.
Falls back to in-memory if Redis unavailable.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

logger = logging.getLogger("server.ratelimit")

# In-memory fallback
_memory_counters: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10  # requests per minute
WINDOW_SECONDS = 60


async def check_rate_limit(ip: str, limit: int = RATE_LIMIT, scope: str = "scan") -> bool:
    """Check if request is within rate limit.

    Args:
        ip: Client IP address
        limit: Max requests per minute (OCR 链路收紧为 5)
        scope: Counter namespace（scan / label），不同链路独立计数

    Returns:
        True if allowed, False if rate limited
    """
    # Try Redis first
    try:
        import redis.asyncio as aioredis

        from shared.config import config

        r = aioredis.from_url(config.redis.url, decode_responses=True)
        key = f"rl:{scope}:{ip}:{int(time.time() // 60)}"

        count = await r.incr(key)
        if count == 1:
            await r.expire(key, WINDOW_SECONDS)

        if count > limit:
            logger.warning("[ratelimit] Rate limited: %s (%d requests)", ip, count)
            return False
        return True

    except Exception:
        # Fallback to in-memory
        return _check_memory(ip, limit, scope)


def _check_memory(ip: str, limit: int, scope: str) -> bool:
    """In-memory rate limiting fallback."""
    now = time.time()
    window_start = now - WINDOW_SECONDS
    key = f"{scope}:{ip}"

    # Clean old entries
    _memory_counters[key] = [
        t for t in _memory_counters[key] if t > window_start
    ]

    if len(_memory_counters[key]) >= limit:
        logger.warning("[ratelimit] Rate limited (memory): %s", ip)
        return False

    _memory_counters[key].append(now)
    return True
