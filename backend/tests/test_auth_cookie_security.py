from __future__ import annotations

from starlette.requests import Request

from api.routes.auth import session_cookie_is_secure


def _request(*, scheme: str = "http", headers: dict[str, str] | None = None) -> Request:
    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": scheme,
            "path": "/auth/login",
            "raw_path": b"/auth/login",
            "query_string": b"",
            "headers": encoded_headers,
            "server": ("127.0.0.1", 8137),
            "client": ("127.0.0.1", 50000),
        }
    )


def test_public_https_proxy_uses_secure_session_cookie():
    request = _request(
        headers={
            "x-forwarded-proto": "https",
            "origin": "https://platform.hedespace.com",
        }
    )

    assert session_cookie_is_secure(request) is True


def test_lan_http_keeps_session_cookie_compatible():
    request = _request(headers={"origin": "http://192.168.10.80:3001"})

    assert session_cookie_is_secure(request) is False


def test_forwarded_protocol_takes_precedence_over_origin():
    request = _request(
        headers={
            "x-forwarded-proto": "http",
            "origin": "https://platform.hedespace.com",
        }
    )

    assert session_cookie_is_secure(request) is False
