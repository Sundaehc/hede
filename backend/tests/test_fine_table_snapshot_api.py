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
