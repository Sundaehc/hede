from storage.vip_repository import JST_FULL_STOCK_HEADER_TO_COLUMN, _decode_xlsx_text


def test_jst_full_stock_brand_header_mapping() -> None:
    assert JST_FULL_STOCK_HEADER_TO_COLUMN["品牌"] == "brand"


def test_jst_full_stock_decodes_excel_escaped_brand_text() -> None:
    assert _decode_xlsx_text("C_x00B0_BANNER") == "C°BANNER"
