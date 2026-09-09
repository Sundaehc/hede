from __future__ import annotations

from types import SimpleNamespace

from api.routes import products
from api.schemas import BatchDeleteRequest


class _Transaction:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return None


class _Repository:
    def __init__(self) -> None:
        self.engine = SimpleNamespace(begin=lambda: _Transaction())
        self.deleted: list[tuple[str, list[int]]] = []

    def is_product_archive_brand(self, brand: str) -> bool:
        return brand in {"cbanner_mens", "cbanner_womens"}

    def get_products_by_ids(self, brand: str, ids: list[int]):
        return [{"id": product_id, "sku": f"{brand}-{product_id}"} for product_id in ids]

    def delete_products(self, brand: str, ids: list[int], *, connection=None) -> int:
        assert connection is not None
        self.deleted.append((brand, ids))
        return len(ids)


def test_batch_delete_groups_same_numeric_id_by_brand(monkeypatch):
    repository = _Repository()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=repository)))
    monkeypatch.setattr(products, "clear_fine_table_cache", lambda: None)
    monkeypatch.setattr(products, "clear_product_goods_cache", lambda: None)
    monkeypatch.setattr(products, "write_operation_log", lambda *_args, **_kwargs: None)

    result = products.batch_delete_products(
        request,
        BatchDeleteRequest.model_validate({
            "items": [
                {"brand": "cbanner_mens", "id": 1},
                {"brand": "cbanner_womens", "id": 1},
            ],
        }),
    )

    assert result["deleted"] == 2
    assert repository.deleted == [
        ("cbanner_mens", [1]),
        ("cbanner_womens", [1]),
    ]
