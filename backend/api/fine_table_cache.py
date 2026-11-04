from __future__ import annotations

from collections import OrderedDict
from sys import getsizeof
from threading import RLock
from time import monotonic
from typing import Any


FineTableCacheKey = tuple[Any, ...]

_MAX_ENTRIES = 160
_TTL_SECONDS = 300
_CACHE: OrderedDict[FineTableCacheKey, tuple[float, dict[str, Any]]] = OrderedDict()
_RESULT_CACHE_MAX_BYTES = 32 * 1024 * 1024
_RESULT_CACHE_MAX_ENTRIES = 8
_RESULT_CACHE: OrderedDict[FineTableCacheKey, tuple[float, dict[str, Any], int]] = OrderedDict()
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


def get_fine_table_result_cache(key: FineTableCacheKey) -> dict[str, Any] | None:
    with _LOCK:
        cached = _RESULT_CACHE.get(key)
        if cached is None:
            return None
        expires_at, payload, _size = cached
        if expires_at <= monotonic():
            _RESULT_CACHE.pop(key, None)
            return None
        _RESULT_CACHE.move_to_end(key)
        return payload


def _result_size(value: Any, seen: set[int]) -> int:
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = getsizeof(value)
    if isinstance(value, dict):
        children = (child for pair in value.items() for child in pair)
    elif isinstance(value, (list, tuple)):
        children = iter(value)
    else:
        return size
    for child in children:
        size += _result_size(child, seen)
        if size > _RESULT_CACHE_MAX_BYTES:
            break
    return size


def set_fine_table_result_cache(key: FineTableCacheKey, payload: dict[str, Any]) -> None:
    # Full results are shared across derived filters and pages, with a byte
    # budget so repeated filtering cannot retain many large product datasets.
    size = _result_size(payload, set())
    if size > _RESULT_CACHE_MAX_BYTES:
        return
    with _LOCK:
        now = monotonic()
        for expired_key in [key for key, entry in _RESULT_CACHE.items() if entry[0] <= now]:
            _RESULT_CACHE.pop(expired_key)
        _RESULT_CACHE.pop(key, None)
        while _RESULT_CACHE and (
            len(_RESULT_CACHE) >= _RESULT_CACHE_MAX_ENTRIES
            or sum(entry[2] for entry in _RESULT_CACHE.values()) + size > _RESULT_CACHE_MAX_BYTES
        ):
            _RESULT_CACHE.popitem(last=False)
        _RESULT_CACHE[key] = (now + _TTL_SECONDS, payload, size)


def clear_fine_table_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _RESULT_CACHE.clear()
