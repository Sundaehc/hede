from datetime import date
from types import SimpleNamespace

from api.routes import fine_table as fine_table_routes


class _BatchResult:
    def __init__(self, batch):
        self.batch = batch

    def mappings(self):
        return self

    def first(self):
        return self.batch


class _Connection:
    def __init__(self, batch):
        self.batch = batch

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        return _BatchResult(self.batch)


class _Engine:
    def __init__(self, batch):
        self.batch = batch

    def connect(self):
        return _Connection(self.batch)


def test_optimized_snapshot_returns_filtered_total(monkeypatch):
    snapshot_date = date(2026, 7, 31)
    batch = {
        "id": 42,
        "brand": "cbanner_mens",
        "snapshot_date": snapshot_date,
        "total_rows": 10,
        "latest_order_date": None,
        "created_at": None,
        "updated_at": None,
    }
    repository = SimpleNamespace(engine=_Engine(batch))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(repository=repository, settings=SimpleNamespace())
        )
    )

    monkeypatch.setattr(fine_table_routes, "_ensure_snapshot_tables", lambda engine: None)
    monkeypatch.setattr(fine_table_routes, "fine_table_snapshot_year_table_exists", lambda engine, value: False)
    monkeypatch.setattr(fine_table_routes, "fine_table_snapshot_ref_table_exists", lambda engine, value: True)
    monkeypatch.setattr(fine_table_routes, "optimized_snapshot_available", lambda engine, value, batch_id: True)
    monkeypatch.setattr(
        fine_table_routes,
        "load_optimized_snapshot_rows",
        lambda engine, value, batch_id, *, conditions, page, page_size: ([{"sku": "A-1"}], 7),
    )
    monkeypatch.setattr(fine_table_routes, "_hydrate_snapshot_image_urls", lambda **kwargs: None)
    monkeypatch.setattr(fine_table_routes, "_hydrate_fine_table_platforms", lambda **kwargs: None)
    monkeypatch.setattr(
        fine_table_routes,
        "_hydrate_snapshot_archive_costs",
        lambda **kwargs: kwargs["items"][0].update(latest_purchase_price=99.2),
    )

    response = fine_table_routes.get_fine_table_snapshot(
        request,
        batch_id=42,
        query=None,
        sku_prefix=None,
        page=1,
        page_size=50,
    )

    assert response["total"] == 7
    assert response["snapshot"]["total_rows"] == 10
    assert response["items"][0]["latest_purchase_price"] == 99.2


def test_optimized_snapshot_sorts_all_filtered_rows_before_pagination(monkeypatch):
    snapshot_date = date(2026, 7, 31)
    batch = {"id": 42, "brand": "cbanner_mens", "snapshot_date": snapshot_date, "total_rows": 1}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=_Engine(batch)), settings=SimpleNamespace(),
    )))
    rows = [
        {"sku": "A-1", "stock_qty": "20", "year": "2025"},
        {"sku": "A-2", "stock_qty": None, "year": "2025"},
        {"sku": "A-3", "stock_qty": "100", "year": "2025"},
        {"sku": "A-4", "stock_qty": "20", "year": "2025"},
        {"sku": "A-5", "stock_qty": "300", "year": "2024"},
    ]

    def load_rows(engine, snapshot_date, batch_id, *, conditions, page, page_size):
        assert page == 1 and page_size is None
        return rows, len(rows)

    monkeypatch.setattr(request.app.state.repository.engine, "dialect", SimpleNamespace(name="sqlite"), raising=False)
    monkeypatch.setattr(fine_table_routes, "_ensure_snapshot_tables", lambda engine: None)
    monkeypatch.setattr(fine_table_routes, "fine_table_snapshot_year_table_exists", lambda engine, value: False)
    monkeypatch.setattr(fine_table_routes, "fine_table_snapshot_ref_table_exists", lambda engine, value: True)
    monkeypatch.setattr(fine_table_routes, "optimized_snapshot_available", lambda engine, value, batch_id: True)
    monkeypatch.setattr(fine_table_routes, "load_optimized_snapshot_rows", load_rows)
    monkeypatch.setattr(fine_table_routes, "_hydrate_snapshot_image_urls", lambda **kwargs: None)
    monkeypatch.setattr(fine_table_routes, "_hydrate_fine_table_platforms", lambda **kwargs: None)
    monkeypatch.setattr(fine_table_routes, "_hydrate_snapshot_archive_costs", lambda **kwargs: None)

    def get_page(page, **kwargs):
        payload = fine_table_routes.get_fine_table_snapshot(
            request, 42, page=page, page_size=2, sort_by="stock_qty",
            filters='[{"field":"year","operator":"in","values":["2025"]}]', **kwargs,
        )
        assert payload["total"] == 4
        return [row["sku"] for row in payload["items"]]

    assert get_page(1) == ["A-3", "A-1"]
    assert get_page(2) == ["A-4", "A-2"]
    assert get_page(1, sort_direction="asc") == ["A-1", "A-4"]
    assert get_page(2, sort_direction="asc") == ["A-3", "A-2"]


def test_live_sort_uses_calendar_dates_and_a_separate_cache_for_each_direction():
    from api.fine_table_cache import clear_fine_table_cache, set_fine_table_result_cache

    brand = "cbanner_mens"
    latest_order_date = "2026-11-21"
    rows = [
        {"sku": "A-1", "daily_sales": [{"date": "2026-11-20", "quantity": 20}]},
        {"sku": "A-2", "daily_sales": [{"date": "2026-11-19", "quantity": 300}]},
        {"sku": "A-3", "daily_sales": [{"date": "2026-11-20", "quantity": 100}]},
    ]
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=None, settings=None)))
    clear_fine_table_cache()
    try:
        set_fine_table_result_cache((brand, "", "", "all", (), None), {
            "items": rows, "total": 3, "latest_order_date": latest_order_date,
        })

        def sku_at(page, direction):
            payload = fine_table_routes.list_fine_table(
                request, brand=brand, page=page, page_size=1,
                sort_by="daily_sales_3_quantity", sort_direction=direction,
            )
            assert payload["total"] == 3
            return payload["items"][0]["sku"]

        assert sku_at(1, "desc") == "A-3"
        assert sku_at(2, "desc") == "A-1"
        assert sku_at(1, "asc") == "A-2"
        assert sku_at(1, "desc") == "A-3"
    finally:
        clear_fine_table_cache()
