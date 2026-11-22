from __future__ import annotations

import re

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from storage.product_image_tokens import TOKEN_PREFIX, is_active_token


_IMAGE_URL_PREFIX = "/images/serve/"
_ALLOWED_IMAGE = re.compile(r"/images/serve/(cbanner_womens|smiley)/([^/\\\x00-\x1f\x7f]{1,200})\.jpg")
_BEARER = re.compile(r"(?i:Bearer) +(" + re.escape(TOKEN_PREFIX) + r"[A-Za-z0-9_-]{43})")
_TOKEN_MARKER = re.compile(r"\b" + re.escape(TOKEN_PREFIX), re.IGNORECASE)
_NO_STORE = {"Cache-Control": "no-store"}
_UNAUTHORIZED = {**_NO_STORE, "WWW-Authenticate": "Bearer"}


async def authorize_product_image_token(request: Request, call_next):
    headers = request.headers.getlist("authorization")
    if not headers:
        return None
    path = request.url.path
    token_supplied = any(_TOKEN_MARKER.search(value) for value in headers)
    if not token_supplied and not path.startswith(_IMAGE_URL_PREFIX):
        return None

    bearer = _BEARER.fullmatch(headers[0]) if len(headers) == 1 else None
    if bearer is None:
        return JSONResponse({"detail": "Invalid image service token"}, 401, headers=_UNAUTHORIZED)
    target = _ALLOWED_IMAGE.fullmatch(path)
    if request.method != "GET" or target is None:
        return JSONResponse({"detail": "Outside image service token scope"}, 403, headers=_NO_STORE)

    engine = getattr(getattr(request.app.state, "auth_repository", None), "engine", None)
    if engine is None:
        return JSONResponse({"detail": "Image token verification unavailable"}, 503, headers=_NO_STORE)
    try:
        active = await run_in_threadpool(is_active_token, engine, bearer[1])
    except SQLAlchemyError:
        return JSONResponse({"detail": "Image token verification unavailable"}, 503, headers=_NO_STORE)
    if not active:
        return JSONResponse({"detail": "Invalid image service token"}, 401, headers=_UNAUTHORIZED)

    request.state.product_image_service_sku = target[2]
    response = await call_next(request)
    response.headers.update(_NO_STORE)
    return response
