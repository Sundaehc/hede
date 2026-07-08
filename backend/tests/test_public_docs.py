from __future__ import annotations

from types import SimpleNamespace

from api.app import _public_read_openapi_schema, create_app
from api.auth_middleware import PUBLIC_PATHS


class _RepositoryStub:
    def create_tables(self):
        pass

    def has_users(self):
        return True


def _create_test_app():
    settings = SimpleNamespace(
        database_url="postgresql://unused",
        frontend_origin="http://localhost:3000",
    )
    repository = _RepositoryStub()
    return create_app(
        settings=settings,
        repository=repository,
        inventory_repository=repository,
        auth_repository=repository,
        operation_log_repository=repository,
        image_matchers={},
    )


def test_public_openapi_schema_only_contains_read_operations():
    schema = _public_read_openapi_schema(_create_test_app())

    methods = {
        method
        for path_item in schema["paths"].values()
        for method in path_item
    }

    assert methods <= {"get", "head"}
    assert schema["paths"]
    assert all(
        not any(keyword in path for keyword in ("admin", "import", "export", "recycle-bin"))
        for path in schema["paths"]
    )
    assert all(not path.startswith("/auth") for path in schema["paths"])
    assert all(not path.startswith("/operation-logs") for path in schema["paths"])


def test_only_public_docs_are_public_without_login():
    assert "/public/docs" in PUBLIC_PATHS
    assert "/public/openapi.json" in PUBLIC_PATHS
    assert "/public/redoc" in PUBLIC_PATHS
    assert "/docs" not in PUBLIC_PATHS
    assert "/openapi.json" not in PUBLIC_PATHS
    assert "/redoc" not in PUBLIC_PATHS
