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


async def check_rate_limit(ip: str) -> bool:
    """Check if request is within rate limit.

    Args:
        ip: Client IP address

    Returns:
        True if allowed, False if rate limited
    """
    # Try Redis first
    try:
        import redis.asyncio as aioredis
        from shared.config import config

        r = aioredis.from_url(config.redis.url, decode_responses=True)
        key = f"rl:{ip}:{int(time.time() // 60)}"

        count = await r.incr(key)
        if count == 1:
            await r.expire(key, WINDOW_SECONDS)

        if count > RATE_LIMIT:
            logger.warning("[ratelimit] Rate limited: %s (%d requests)", ip, count)
            return False
        return True

    except Exception:
        # Fallback to in-memory
        return _check_memory(ip)


def _check_memory(ip: str) -> bool:
    """In-memory rate limiting fallback."""
    now = time.time()
    window_start = now - WINDOW_SECONDS

    # Clean old entries
    _memory_counters[ip] = [
        t for t in _memory_counters[ip] if t > window_start
    ]

    if len(_memory_counters[ip]) >= RATE_LIMIT:
        logger.warning("[ratelimit] Rate limited (memory): %s", ip)
        return False

    _memory_counters[ip].append(now)
    return True