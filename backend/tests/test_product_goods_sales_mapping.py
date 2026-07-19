from api.routes.product_goods import _resolve_jst_product_code
from domain.product_goods_historical_sales_schema import product_goods_historical_sales_table_for_year


def test_jst_sales_code_maps_to_the_longest_matching_goods_code():
    matched = _resolve_jst_product_code(
        "C0152140L0101250",
        "C0152140L01",
        ["C0152140L01", "C0152140L0101"],
        {"C0152140L01": "C0152140L01"},
    )

    assert matched == "C0152140L0101"


def test_size_suffixed_sales_code_maps_to_base_goods_code():
    assert _resolve_jst_product_code(
        "Q9941832W5252235",
        "Q9941832W52",
        ["Q9941832W52"],
        {"Q9941832W52": "Q9941832W52"},
    ) == "Q9941832W52"


def test_jst_sales_code_uses_style_only_when_it_is_unique():
    assert _resolve_jst_product_code("unmatched", "STYLE-1", ["SKU-1"], {"STYLE-1": "SKU-1"}) == "SKU-1"
    assert _resolve_jst_product_code("unmatched", "STYLE-1", ["SKU-1", "SKU-2"], {}) is None


def test_historical_sales_source_rows_are_immutable():
    table = product_goods_historical_sales_table_for_year(2024)
    assert table.name == "product_goods_historical_sales_2024"
    assert {"brand", "source_workbook", "source_sheet", "source_row_number"} <= set(table.c.keys())
    assert any(
        constraint.name == "uq_product_goods_historical_sales_2024_source_row"
        for constraint in table.constraints
    )
    assert any(index.name == "idx_product_goods_historical_sales_2024_brand_product" for index in table.indexes)
