"""Cache module: L1 TTLCache + L2 Redis."""

from server.app.cache.multi_cache import cache_get, cache_put

__all__ = ["cache_get", "cache_put"]