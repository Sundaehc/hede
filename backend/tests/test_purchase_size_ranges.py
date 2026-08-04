from decimal import Decimal

from api.routes import inventory
from api.routes.inventory import _parse_purchase_size_range_labels


def test_purchase_size_range_expands_eu_sizes():
    assert _parse_purchase_size_range_labels("38-43") == ("38", "39", "40", "41", "42", "43")


def test_purchase_size_range_preserves_discrete_labels():
    assert _parse_purchase_size_range_labels("S、M、L") == ("S", "M", "L")


def test_purchase_size_range_expands_millimeter_sizes():
    assert _parse_purchase_size_range_labels("220-235") == ("220", "225", "230", "235")


def test_purchase_detail_lookup_checks_other_product_archives_for_size_range(monkeypatch):
    calls: list[str] = []

    def fake_lookup(_connection, _product_code, _quantity, brand):
        calls.append(brand)
        is_eblan = brand == "eblan"
        return {
            "product_code": "SKU-001",
            "size_range": "38-43" if is_eblan else None,
            "size_labels": ["38", "39", "40", "41", "42", "43"] if is_eblan else [],
            "_matched_product": brand in {"cbanner_mens", "eblan"},
        }

    monkeypatch.setattr(inventory, "_build_purchase_detail_lookup_for_brand", fake_lookup)

    item = inventory._build_purchase_detail_lookup(None, "SKU-001", Decimal("0"), "cbanner_mens")

    assert "eblan" in calls
    assert item["size_range"] == "38-43"
    assert item["size_labels"] == ["38", "39", "40", "41", "42", "43"]
