from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from time import monotonic
from typing import Any


FineTableCacheKey = tuple[str, str, str, str, int, int]

_MAX_ENTRIES = 160
_TTL_SECONDS = 300
_CACHE: OrderedDict[FineTableCacheKey, tuple[float, dict[str, Any]]] = OrderedDict()
_LOCK = RLock()


def get_fine_table_cache(key: FineTableCacheKey) -> dict[str, Any] | None:
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            return None

        expires_at, payload = cached
        if expires_at <= monotonic():
            _CACHE.pop(key, None)
            return None

        _CACHE.move_to_end(key)
        return payload


def set_fine_table_cache(key: FineTableCacheKey, payload: dict[str, Any]) -> None:
    with _LOCK:
        _CACHE[key] = (monotonic() + _TTL_SECONDS, payload)
        _CACHE.move_to_end(key)

        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)


def clear_fine_table_cache() -> None:
    with _LOCK:
        _CACHE.clear()
