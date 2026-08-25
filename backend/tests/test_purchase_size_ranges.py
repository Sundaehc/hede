from decimal import Decimal

from api.routes import inventory
from api.routes.inventory import _parse_purchase_size_range_labels


def test_purchase_size_range_expands_eu_sizes():
    assert _parse_purchase_size_range_labels("38-43") == ("38", "39", "40", "41", "42", "43")


def test_purchase_size_range_preserves_discrete_labels():
    assert _parse_purchase_size_range_labels("S、M、L") == ("S", "M", "L")


def test_purchase_size_range_expands_millimeter_sizes():
    assert _parse_purchase_size_range_labels("220-235") == ("220", "225", "230", "235")


def test_purchase_import_parses_ns_color_coded_eu_size():
    assert inventory._split_purchase_size_code("NAA2656001A020634", "ns") == ("NAA2656001A02", "34")
    assert inventory._split_purchase_product_code("NAA2656001A020634", [], "ns") == (
        "NAA2656001A02",
        "NAA2656001A02",
        "06",
        "",
        "34",
    )


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
    assert item["matched_product"] is True
    assert item["size_range"] == "38-43"
    assert item["size_labels"] == ["38", "39", "40", "41", "42", "43"]


def test_purchase_detail_lookup_checks_smiley_archive_when_brand_is_unknown(monkeypatch):
    calls: list[str] = []

    def fake_lookup(_connection, _product_code, _quantity, brand):
        calls.append(brand)
        is_smiley = brand == "smiley"
        return {
            "product_code": "6975771256717",
            "size_range": "笑脸男鞋尺码组38-44" if is_smiley else None,
            "size_labels": ["38", "39", "40", "41", "42", "43", "44"] if is_smiley else [],
            "_matched_product": is_smiley,
        }

    monkeypatch.setattr(inventory, "_build_purchase_detail_lookup_for_brand", fake_lookup)

    item = inventory._build_purchase_detail_lookup(None, "6975771256717", Decimal("0"), "cbanner_mens")

    assert "smiley" in calls
    assert item["matched_product"] is True
    assert item["size_range"] == "笑脸男鞋尺码组38-44"
    assert item["size_labels"] == ["38", "39", "40", "41", "42", "43", "44"]


def test_purchase_detail_lookup_checks_ni_archive_when_brand_is_unknown(monkeypatch):
    calls: list[str] = []

    def fake_lookup(_connection, _product_code, _quantity, brand):
        calls.append(brand)
        is_ni = brand == "ni"
        return {
            "product_code": "NI-001",
            "size_range": "NI尺码组35-40" if is_ni else None,
            "size_labels": ["35", "36", "37", "38", "39", "40"] if is_ni else [],
            "_matched_product": is_ni,
        }

    monkeypatch.setattr(inventory, "_build_purchase_detail_lookup_for_brand", fake_lookup)

    item = inventory._build_purchase_detail_lookup(None, "NI-001", Decimal("0"), "cbanner_mens")

    assert "ni" in calls
    assert item["matched_product"] is True
    assert item["size_range"] == "NI尺码组35-40"
    assert item["size_labels"] == ["35", "36", "37", "38", "39", "40"]


def test_purchase_detail_lookup_marks_unmatched_partial_code(monkeypatch):
    def fake_lookup(_connection, product_code, _quantity, _brand):
        return {
            "product_code": product_code[:-2],
            "size_range": None,
            "size_labels": [],
            "_matched_product": False,
        }

    monkeypatch.setattr(inventory, "_build_purchase_detail_lookup_for_brand", fake_lookup)

    item = inventory._build_purchase_detail_lookup(None, "SKU-PARTIAL35", Decimal("0"), "cbanner_mens")

    assert item["matched_product"] is False
    assert item["product_code"] == "SKU-PARTIAL"
