from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from math import ceil, floor
from threading import Lock
import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class _TokenBucketLimiter:
    """A small in-process limiter suitable for a single Uvicorn worker."""

    def __init__(
        self,
        *,
        requests: int,
        window_seconds: int,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.requests = max(1, requests)
        self.window_seconds = max(1, window_seconds)
        self.burst = max(0, burst)
        self.rate = self.requests / self.window_seconds
        self.capacity = float(self.requests + self.burst)
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        now = self._clock()
        with self._lock:
            self._remove_idle_buckets(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated_at=now)
                self._buckets[key] = bucket

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate)
            bucket.updated_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                retry_after = 0
                allowed = True
            else:
                retry_after = max(1, ceil((1.0 - bucket.tokens) / self.rate))
                allowed = False

            remaining = max(0, floor(bucket.tokens))
            return allowed, remaining, retry_after

    def _remove_idle_buckets(self, now: float) -> None:
        # Do not allow an IP map to grow forever when the service is internet-facing.
        idle_after = max(self.window_seconds, 60) * 2
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.updated_at > idle_after
        ]
        for key in stale_keys:
            self._buckets.pop(key, None)


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def _client_ip(request: Request, trusted_proxy_ips: frozenset[str]) -> str:
    peer_ip = _valid_ip(request.client.host if request.client else None)
    if peer_ip in trusted_proxy_ips:
        # Only trust forwarding headers from explicitly configured proxy peers.
        forwarded_for = request.headers.get("x-forwarded-for", "")
        for candidate in forwarded_for.split(","):
            forwarded_ip = _valid_ip(candidate)
            if forwarded_ip:
                return forwarded_ip
        real_ip = _valid_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return real_ip
    return peer_ip or "unknown"


class RequestRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        enabled: bool = True,
        requests: int = 120,
        window_seconds: int = 60,
        burst: int = 20,
        trusted_proxy_ips: tuple[str, ...] | list[str] | set[str] = (),
    ) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.requests = max(1, requests)
        self.window_seconds = max(1, window_seconds)
        self.burst = max(0, burst)
        self.trusted_proxy_ips = frozenset(
            normalized
            for value in trusted_proxy_ips
            if (normalized := _valid_ip(value)) is not None
        )
        self.limiter = _TokenBucketLimiter(
            requests=self.requests,
            window_seconds=self.window_seconds,
            burst=self.burst,
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled or request.method == "OPTIONS":
            return await call_next(request)

        client_ip = _client_ip(request, self.trusted_proxy_ips)
        allowed, remaining, retry_after = self.limiter.check(client_ip)
        headers = {
            "X-RateLimit-Limit": str(self.requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(time.time()) + (retry_after or self.window_seconds)),
        }
        if not allowed:
            headers["Retry-After"] = str(retry_after)
            return JSONResponse(
                {"detail": "请求过于频繁，请稍后再试"},
                status_code=429,
                headers=headers,
            )

        response = await call_next(request)
        for name, value in headers.items():
            response.headers[name] = value
        return response
