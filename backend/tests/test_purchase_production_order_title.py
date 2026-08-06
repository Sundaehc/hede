from api.routes.inventory import (
    CBANNER_MENS_BRAND,
    CBANNER_WOMENS_BRAND,
    EBLAN_BRAND,
    YANDOU_BRAND,
    PURCHASE_PRODUCTION_FIXED_HEADERS,
    _purchase_production_detail_rows,
    _purchase_production_size_labels,
    _purchase_production_order_title,
)


def test_production_purchase_order_title_uses_supplier_brand():
    assert _purchase_production_order_title(CBANNER_MENS_BRAND) == "赫德电商（千百度）生产采购单"
    assert _purchase_production_order_title(CBANNER_WOMENS_BRAND) == "赫德电商（千百度）生产采购单"
    assert _purchase_production_order_title(EBLAN_BRAND) == "赫德电商（伊伴）生产采购单"
    assert _purchase_production_order_title(YANDOU_BRAND) == "赫德电商（名人烟斗）生产采购单"


def test_production_purchase_order_title_does_not_mislabel_unknown_brand():
    assert _purchase_production_order_title("unknown") == "赫德电商生产采购单"


def test_production_purchase_export_keeps_zero_size_columns_and_values():
    details = [{
        "product_code": "QB123",
        "quantity": "1",
        "unit_price": "10",
        "size_quantities": {"235": "0", "240": "1"},
        "extra_fields": {},
    }]

    size_labels = _purchase_production_size_labels(details)
    rows = _purchase_production_detail_rows(details, size_labels, "")

    assert "235" in size_labels
    assert rows[0][len(PURCHASE_PRODUCTION_FIXED_HEADERS)] == "0"
