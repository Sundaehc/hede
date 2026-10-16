from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from api.auth_middleware import auth_middleware
from api.routes import auth as auth_routes
from api.routes import inventory as inventory_routes


class AuthRepository:
    def has_users(self):
        return True

    def get_user_by_session(self, token):
        if token != "test-session":
            return None
        return {
            "id": 1, "username": "test", "role_code": "super_admin",
            "department_code": "开发部", "permissions": ["*"],
            "password_hash": "not-returned",
        }


def _app(repository=None):
    app = FastAPI()
    app.state.auth_repository = AuthRepository()
    app.state.inventory_repository = repository or SimpleNamespace()
    app.middleware("http")(auth_middleware)
    app.include_router(auth_routes.router)
    app.include_router(inventory_routes.router)

    @app.get("/public/docs")
    async def public_probe():
        return {"status": "ok"}

    return app


@pytest.mark.parametrize("path, target", [
    ("/inventory/import-template/preview", "read_template_documents"),
    ("/inventory/import-template", "read_template_documents"),
    ("/inventory/import-purchase", "_read_purchase_import_rows"),
    ("/inventory/import", "load_workbook"),
    ("/inventory/1/details/import-replace", "get_record"),
])
def test_login_validation_remains_responsive_during_inventory_import(monkeypatch, path, target):
    started = threading.Event()
    release = threading.Event()
    worker_threads = []

    def slow_import(*_args, **_kwargs):
        worker_threads.append(threading.get_ident())
        started.set()
        if not release.wait(3):
            raise RuntimeError("Import blocked the event loop")
        raise HTTPException(status_code=400, detail="Controlled import error")

    repository = SimpleNamespace()
    if target == "get_record":
        repository.get_record = slow_import
    else:
        monkeypatch.setattr(inventory_routes, target, slow_import)
    app = _app(repository)

    async def exercise():
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            cookies={"hede_session": "test-session"},
        ) as client:
            pending_import = asyncio.create_task(client.post(
                path, data={"document_type": "进货单"},
                files={"file": ("import.xlsx", b"test", "application/octet-stream")},
            ))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                assert len(worker_threads) == 1
                assert worker_threads[0] != loop_thread
                response = await asyncio.wait_for(client.get("/auth/me"), timeout=1)
                assert response.status_code == 200
                assert response.json()["user"]["username"] == "test"
                assert "password_hash" not in response.json()["user"]
                assert not pending_import.done()
            finally:
                release.set()
                imported = await asyncio.wait_for(pending_import, timeout=3)
            assert imported.status_code == 400
            expected_error = "Invalid Excel file" if target == "load_workbook" else "Controlled import error"
            assert imported.json() == {"detail": expected_error}

    asyncio.run(exercise())


@pytest.mark.parametrize("method", ["has_users", "get_user_by_session"])
def test_slow_authentication_database_calls_do_not_block_other_requests(method):
    started = threading.Event()
    release = threading.Event()
    worker_threads = []
    app = _app()
    original = getattr(app.state.auth_repository, method)

    def slow_auth(*args):
        worker_threads.append(threading.get_ident())
        started.set()
        if not release.wait(3):
            raise RuntimeError("Authentication blocked the event loop")
        return original(*args)

    setattr(app.state.auth_repository, method, slow_auth)

    async def exercise():
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
            cookies={"hede_session": "test-session"},
        ) as client:
            authentication = asyncio.create_task(client.get("/auth/me"))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                assert worker_threads[0] != loop_thread
                response = await asyncio.wait_for(client.get("/public/docs"), timeout=1)
                assert response.status_code == 200
                assert not authentication.done()
            finally:
                release.set()
                authenticated = await asyncio.wait_for(authentication, timeout=3)
            assert authenticated.status_code == 200

    asyncio.run(exercise())


def test_unauthenticated_inventory_import_never_runs_the_parser(monkeypatch):
    def unexpected_parse(*_args, **_kwargs):
        pytest.fail("Unauthenticated requests must not start an import")

    monkeypatch.setattr(inventory_routes, "_read_purchase_import_rows", unexpected_parse)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app()), base_url="http://test",
        ) as client:
            response = await client.post(
                "/inventory/import-purchase",
                files={"file": ("import.xlsx", b"test", "application/octet-stream")},
            )
            assert response.status_code == 401

    asyncio.run(exercise())
