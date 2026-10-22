from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import MetaData, create_engine, event

from api.auth_middleware import auth_middleware
from api.routes import products
from api.schemas import BatchDeleteRequest, ProductSelectionFilters
from domain.schema import PRODUCT_ARCHIVE_TABLES, build_product_archive_table
from storage import product_repository as repository_module
from storage.product_repository import ProductRepository


@pytest.fixture
def selection_repository(monkeypatch):
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value))
    monkeypatch.setattr(repository_module, "not_excluded_sku_condition", lambda sku, _original: sku != "EXCLUDED")
    tables = {
        "cbanner_mens": PRODUCT_ARCHIVE_TABLES["cbanner_mens"],
        "cbanner_womens": PRODUCT_ARCHIVE_TABLES["cbanner_womens"],
        "new_brand": build_product_archive_table("manual_product_archive_99", metadata=MetaData()),
    }
    for table in tables.values():
        table.create(engine)
        with engine.begin() as connection:
            connection.execute(table.insert(), [
                {
                    "id": product_id, "sku": sku, "original_sku": original_sku, "year": year,
                    "source_workbook": "test", "source_sheet": "test", "source_row_number": str(product_id), "raw_payload": {},
                    "deleted_at": datetime(2026, 10, 1) if product_id == 5 else None,
                }
                for product_id, sku, original_sku, year in [
                    (1, "AA-1", "ORIG-1", "2026"), (2, "BB-2", "AA-2", "26年春季款"),
                    (3, "AA-3", "ORIG-3", "2025"), (4, "CC-4", "ORIG-4", None),
                    (5, "AA-5", "AA-5", "2026"), (6, "EXCLUDED", "AA-6", "2026"),
                ]
            ])
    repository = object.__new__(ProductRepository)
    repository.engine = engine
    repository._table_for_brand = tables.__getitem__
    repository.product_archive_brands = lambda: list(tables)
    repository.is_product_archive_brand = tables.__contains__
    try:
        yield repository
    finally:
        engine.dispose()


@pytest.mark.parametrize("filters", [
    {"brand": "all"},
    {"brand": "all", "query": "AA,CC"},
    {"brand": "all", "sku_prefix": "AA", "year": "2025"},
    {"brand": "cbanner_mens", "year": "2026"},
    {"brand": "cbanner_womens", "query": "1\n2", "sku_prefix": "AA", "year": "2026"},
    {"brand": "new_brand", "sku_prefix": "AA", "year": "2025"},
    {"brand": "new_brand", "query": "missing"},
])
def test_full_selection_matches_listing_filters_across_every_page(selection_repository, filters):
    brand = filters["brand"]
    list_filters = {key: value for key, value in filters.items() if key != "brand"}
    expected = set()
    for page in range(1, 14):
        if brand == "all":
            listed = selection_repository.list_all_products(query=list_filters.get("query"), sku_prefix=list_filters.get("sku_prefix"), page=page, page_size=1)
        else:
            listed = selection_repository.list_products(brand, query=list_filters.get("query"), sku_prefix=list_filters.get("sku_prefix"), year=list_filters.get("year"), page=page, page_size=1)
        expected.update((item.get("brand", brand), item["id"]) for item in listed["items"])
    targets = selection_repository.list_product_targets(**filters)
    assert {(item["brand"], item["id"]) for item in targets} == expected
    assert len(targets) == len(expected)
    assert all(item["id"] not in {5, 6} for item in targets)


def test_selection_projects_only_brand_and_id_without_paging_or_full_rows(selection_repository):
    statements = []
    event.listen(selection_repository.engine, "before_cursor_execute", lambda _connection, _cursor, statement, _parameters, _context, _executemany: statements.append(statement))
    targets = selection_repository.list_product_targets(brand="all")
    assert len(targets) == 12
    assert len(statements) == 1
    assert "LIMIT" not in statements[0] and "count(" not in statements[0]
    assert "raw_payload" not in statements[0] and "cost_price" not in statements[0]
    assert all(set(item) == {"brand", "id"} for item in targets)
    assert {item["brand"] for item in targets if item["id"] == 1} == {"cbanner_mens", "cbanner_womens", "new_brand"}


def test_selection_snapshot_does_not_delete_later_inserts(selection_repository):
    targets = selection_repository.list_product_targets(brand="new_brand", sku_prefix="AA")
    assert {item["id"] for item in targets} == {1, 2, 3}
    table = selection_repository._table_for_brand("new_brand")
    with selection_repository.engine.begin() as connection:
        connection.execute(table.insert(), {
            "id": 10, "sku": "AA-10", "source_workbook": "test", "source_sheet": "test", "source_row_number": "10", "raw_payload": {},
        })
    assert selection_repository.delete_products("new_brand", [item["id"] for item in targets]) == 3
    assert selection_repository.get_product("new_brand", 10) is not None


def test_large_batch_is_chunked_and_rolls_back_all_chunks_on_error(selection_repository):
    table = selection_repository._table_for_brand("new_brand")
    ids = list(range(100, 2305))
    with selection_repository.engine.begin() as connection:
        connection.execute(table.insert(), [
            {"id": product_id, "sku": f"LARGE-{product_id}", "source_workbook": "test", "source_sheet": "test", "source_row_number": str(product_id), "raw_payload": {}}
            for product_id in ids
        ])
    statements = []

    def interrupt_second_chunk(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("UPDATE manual_product_archive_99"):
            statements.append(statement)
            if len(statements) == 2:
                raise RuntimeError("interrupted batch")

    event.listen(selection_repository.engine, "before_cursor_execute", interrupt_second_chunk)
    with pytest.raises(RuntimeError, match="interrupted batch"):
        selection_repository.delete_products("new_brand", ids)
    event.remove(selection_repository.engine, "before_cursor_execute", interrupt_second_chunk)
    assert len(selection_repository.get_products_by_ids("new_brand", ids + [100, 5])) == 2205
    assert selection_repository.delete_products("new_brand", ids + [100, 5]) == 2205
    assert selection_repository.get_products_by_ids("new_brand", ids) == []


def test_selection_endpoint_uses_exact_filters_and_disables_caching():
    repository = SimpleNamespace(is_product_archive_brand=Mock(return_value=True), list_product_targets=Mock(return_value=[{"brand": "new_brand", "id": 7}]))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=repository)))
    filters = {"brand": "new_brand", "query": "AA", "sku_prefix": "A", "year": "2026"}
    response = products.list_product_selection_ids(request, ProductSelectionFilters(**filters))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    repository.list_product_targets.assert_called_once_with(**filters)
    assert b'"total":1' in response.body


def test_cross_brand_batch_delete_rolls_back_every_brand_on_failure(selection_repository, monkeypatch):
    original_delete = selection_repository.delete_products

    def delete_then_fail(brand, ids, *, connection=None):
        deleted = original_delete(brand, ids, connection=connection)
        if brand == "cbanner_womens":
            raise RuntimeError("interrupted brand")
        return deleted

    monkeypatch.setattr(selection_repository, "delete_products", delete_then_fail)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=selection_repository)))
    with pytest.raises(RuntimeError, match="interrupted brand"):
        products.batch_delete_products(request, BatchDeleteRequest(items=[
            {"brand": "cbanner_mens", "id": 1}, {"brand": "cbanner_womens", "id": 1},
        ]))
    assert selection_repository.get_product("cbanner_mens", 1) is not None
    assert selection_repository.get_product("cbanner_womens", 1) is not None


@pytest.mark.parametrize("permissions,expected", [([], 403), (["product.view"], 403), (["product.manage"], 200), (["*"], 200)])
def test_selection_endpoint_requires_management_permission(permissions, expected):
    repository = SimpleNamespace(is_product_archive_brand=Mock(return_value=True), list_product_targets=Mock(return_value=[]))
    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.state.auth_repository = SimpleNamespace(has_users=lambda: True, get_user_by_session=lambda _session: {"id": 1, "permissions": permissions})
    app.state.repository = repository
    app.include_router(products.router)
    with TestClient(app) as client:
        response = client.post("/products/selection-ids", json={"brand": "all"})
    assert response.status_code == expected
    assert repository.list_product_targets.called is (expected == 200)


def test_selection_rejects_unknown_brands_or_filters_without_loading_targets():
    repository = SimpleNamespace(is_product_archive_brand=Mock(return_value=False), list_product_targets=Mock())
    app = FastAPI()
    app.state.repository = repository
    app.include_router(products.router)
    with TestClient(app) as client:
        assert client.post("/products/selection-ids", json={"brand": "unknown"}).status_code == 400
        for body in ({"brand": "all", "page": 2}, {"brand": "all", "page_size": 10}, {"query": "AA"}):
            assert client.post("/products/selection-ids", json=body).status_code == 422
    repository.list_product_targets.assert_not_called()
