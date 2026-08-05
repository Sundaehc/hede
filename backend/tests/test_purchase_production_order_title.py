from api.routes.inventory import (
    CBANNER_MENS_BRAND,
    CBANNER_WOMENS_BRAND,
    EBLAN_BRAND,
    YANDOU_BRAND,
    _purchase_production_order_title,
)


def test_production_purchase_order_title_uses_supplier_brand():
    assert _purchase_production_order_title(CBANNER_MENS_BRAND) == "赫德电商（千百度）生产采购单"
    assert _purchase_production_order_title(CBANNER_WOMENS_BRAND) == "赫德电商（千百度）生产采购单"
    assert _purchase_production_order_title(EBLAN_BRAND) == "赫德电商（伊伴）生产采购单"
    assert _purchase_production_order_title(YANDOU_BRAND) == "赫德电商（名人烟斗）生产采购单"


def test_production_purchase_order_title_does_not_mislabel_unknown_brand():
    assert _purchase_production_order_title("unknown") == "赫德电商生产采购单"
