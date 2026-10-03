"""Multi-level cache: L1 TTLCache (in-process) + L2 Redis.

From 06 doc section 六·多级缓存实现:
    - L1: cachetools.TTLCache(maxsize=10_000, ttl=300) - microsecond
    - L2: Redis - millisecond
    - Cache keys: wine:bc:{barcode}
    - Empty/NOT_WINE markers with TTL
"""

from __future__ import annotations

import json
import logging
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger("server.cache")

# L1: in-process TTL cache (5 min, 10k entries)
_l1: TTLCache[str, dict[str, Any] | None] = TTLCache(maxsize=10_000, ttl=300)

# L2: Redis client (lazy init)
_redis = None


def _get_redis():
    """Lazy Redis connection."""
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as aioredis
            from shared.config import config

            _redis = aioredis.from_url(
                config.redis.url, decode_responses=True
            )
        except Exception:
            logger.warning("[cache] Redis not available, L2 disabled")
            _redis = False  # type: ignore[assignment]
    return _redis


async def cache_get(barcode: str) -> dict[str, Any] | None:
    """Get from cache. Returns dict or None if miss.

    Args:
        barcode: Barcode string

    Returns:
        Cached response dict, or None on cache miss
    """
    # L1 check
    if barcode in _l1:
        logger.debug("[cache] L1 hit: %s", barcode)
        return _l1[barcode]

    # L2 check
    r = _get_redis()
    if r and r is not False:
        try:
            raw = await r.get(f"wine:bc:{barcode}")
            if raw:
                hit = json.loads(raw)
                _l1[barcode] = hit  # Write-back to L1
                logger.debug("[cache] L2 hit: %s", barcode)
                return hit
        except Exception:
            logger.warning("[cache] L2 read error for %s", barcode)

    return None


async def cache_put(barcode: str, resp: dict[str, Any], ttl: int = 604800) -> None:
    """Write to both L1 and L2.

    Args:
        barcode: Barcode string
        resp: Response dict to cache
        ttl: Redis TTL in seconds (default 7 days)
    """
    # L1
    _l1[barcode] = resp

    # L2
    r = _get_redis()
    if r and r is not False:
        try:
            await r.set(
                f"wine:bc:{barcode}",
                json.dumps(resp, ensure_ascii=False),
                ex=ttl,
            )
            logger.debug("[cache] L2 write: %s (ttl=%ds)", barcode, ttl)
        except Exception:
            logger.warning("[cache] L2 write error for %s", barcode)


async def cache_delete(barcode: str) -> None:
    """Delete from both L1 and L2."""
    _l1.pop(barcode, None)

    r = _get_redis()
    if r and r is not False:
        try:
            await r.delete(f"wine:bc:{barcode}")
        except Exception:
            pass