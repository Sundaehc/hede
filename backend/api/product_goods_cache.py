from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from time import monotonic
from typing import Any


ProductGoodsCacheKey = tuple[Any, ...]

_MAX_ENTRIES = 160
_TTL_SECONDS = 300
_CACHE: OrderedDict[ProductGoodsCacheKey, tuple[float, dict[str, Any]]] = OrderedDict()
_FILTER_CACHE_MAX_ENTRIES = 80
_FILTER_CACHE_TTL_SECONDS = 60
_FILTER_CACHE: OrderedDict[ProductGoodsCacheKey, tuple[float, dict[str, Any]]] = OrderedDict()
_RISK_CODES_CACHE_TTL_SECONDS = 300
_RISK_CODES_CACHE: OrderedDict[str, tuple[float, tuple[str, ...]]] = OrderedDict()
_LOCK = RLock()


def get_product_goods_cache(key: ProductGoodsCacheKey) -> dict[str, Any] | None:
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


def set_product_goods_cache(key: ProductGoodsCacheKey, payload: dict[str, Any]) -> None:
    with _LOCK:
        _CACHE[key] = (monotonic() + _TTL_SECONDS, payload)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)


def get_product_goods_filter_options_cache(key: ProductGoodsCacheKey) -> dict[str, Any] | None:
    with _LOCK:
        cached = _FILTER_CACHE.get(key)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= monotonic():
            _FILTER_CACHE.pop(key, None)
            return None
        _FILTER_CACHE.move_to_end(key)
        return payload


def set_product_goods_filter_options_cache(key: ProductGoodsCacheKey, payload: dict[str, Any]) -> None:
    with _LOCK:
        _FILTER_CACHE[key] = (monotonic() + _FILTER_CACHE_TTL_SECONDS, payload)
        _FILTER_CACHE.move_to_end(key)
        while len(_FILTER_CACHE) > _FILTER_CACHE_MAX_ENTRIES:
            _FILTER_CACHE.popitem(last=False)


def get_product_goods_risk_codes_cache(brand: str) -> tuple[str, ...] | None:
    with _LOCK:
        cached = _RISK_CODES_CACHE.get(brand)
        if cached is None:
            return None
        expires_at, product_codes = cached
        if expires_at <= monotonic():
            _RISK_CODES_CACHE.pop(brand, None)
            return None
        _RISK_CODES_CACHE.move_to_end(brand)
        return product_codes


def set_product_goods_risk_codes_cache(brand: str, product_codes: set[str]) -> None:
    with _LOCK:
        _RISK_CODES_CACHE[brand] = (
            monotonic() + _RISK_CODES_CACHE_TTL_SECONDS,
            tuple(sorted(product_codes)),
        )
        _RISK_CODES_CACHE.move_to_end(brand)
        while len(_RISK_CODES_CACHE) > 4:
            _RISK_CODES_CACHE.popitem(last=False)


def clear_product_goods_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _FILTER_CACHE.clear()
        _RISK_CODES_CACHE.clear()
