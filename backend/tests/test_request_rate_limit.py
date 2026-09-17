from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.request_rate_limit import (
    RequestRateLimitMiddleware,
    _TokenBucketLimiter,
    _client_ip,
)


def _client(**middleware_options) -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    app.add_middleware(RequestRateLimitMiddleware, **middleware_options)
    return TestClient(app)


def test_limiter_rejects_requests_after_capacity_is_exhausted():
    client = _client(requests=2, window_seconds=60, burst=0)

    first = client.get("/health")
    second = client.get("/health")
    third = client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json() == {"detail": "请求过于频繁，请稍后再试"}
    assert third.headers["retry-after"] == "30"
    assert third.headers["x-ratelimit-limit"] == "2"
    assert third.headers["x-ratelimit-remaining"] == "0"


def test_different_forwarded_clients_are_limited_independently_when_proxy_is_trusted():
    def request_with_forwarded_ip(forwarded_ip: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/health",
                "headers": [(b"x-forwarded-for", forwarded_ip.encode())],
                "client": ("127.0.0.1", 12345),
                "server": ("127.0.0.1", 8000),
                "scheme": "http",
            }
        )

    trusted_proxies = frozenset({"127.0.0.1"})

    assert _client_ip(
        request_with_forwarded_ip("192.168.10.21"), trusted_proxies
    ) == "192.168.10.21"
    assert _client_ip(
        request_with_forwarded_ip("192.168.10.22"), trusted_proxies
    ) == "192.168.10.22"

    limiter = _TokenBucketLimiter(
        requests=1,
        window_seconds=60,
        burst=0,
    )
    assert limiter.check("192.168.10.21")[0] is True
    assert limiter.check("192.168.10.21")[0] is False
    assert limiter.check("192.168.10.22")[0] is True


def test_forwarded_headers_are_ignored_without_a_trusted_proxy():
    client = _client(requests=1, window_seconds=60, burst=0)

    first = client.get("/health", headers={"X-Forwarded-For": "192.168.10.21"})
    second = client.get("/health", headers={"X-Forwarded-For": "192.168.10.22"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_options_requests_are_not_rate_limited():
    client = _client(requests=1, window_seconds=60, burst=0)

    first = client.options("/health")
    second = client.options("/health")

    assert first.status_code == 405
    assert second.status_code == 405


def test_disabled_limiter_does_not_add_limit_headers_or_reject_requests():
    client = _client(enabled=False, requests=1, window_seconds=60, burst=0)

    responses = [client.get("/health") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert "x-ratelimit-limit" not in responses[0].headers


def test_token_bucket_refills_using_the_configured_rate():
    now = [0.0]
    limiter = _TokenBucketLimiter(
        requests=2,
        window_seconds=10,
        burst=0,
        clock=lambda: now[0],
    )

    assert limiter.check("client")[0] is True
    assert limiter.check("client")[0] is True
    assert limiter.check("client")[0] is False
    now[0] = 5.0
    assert limiter.check("client")[0] is True
