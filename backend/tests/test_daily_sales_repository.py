from datetime import date

from domain.daily_sales_schema import jst_daily_sales_table_for_year, vip_daily_sales_table_for_year
from storage.daily_sales_repository import DailySalesRepository


def test_daily_sales_year_tables_have_expected_business_keys():
    jst_table = jst_daily_sales_table_for_year(2026)
    vip_table = vip_daily_sales_table_for_year(2026)

    assert jst_table.name == "jst_daily_sales_2026"
    assert {"sales_date", "channel", "product_code", "barcode", "raw_payload"} <= set(jst_table.c.keys())
    assert vip_table.name == "vip_daily_sales_2026"
    assert {"sales_date", "goods_id", "size_id", "sales_quantity", "raw_payload"} <= set(vip_table.c.keys())


def test_jst_daily_sales_mapping_and_key_are_stable():
    mapped = DailySalesRepository._map_jst(
        {
            "渠道": "天猫",
            "商品编码": "SKU-34",
            "款式编码": "STYLE-1",
            "颜色规格": "黑色/34",
            "渠道编码": "TMALL",
            "国标码": "690000000001",
            "销售数量": 3,
            "净销量": 2,
            "销售金额": "599.00",
        }
    )
    mapped["sales_date"] = date(2026, 7, 18)

    assert mapped["sales_quantity"] == 3
    assert mapped["net_sales_quantity"] == 2
    assert str(mapped["sales_amount"]) == "599.00"
    assert DailySalesRepository._jst_key(mapped) == (
        date(2026, 7, 18), "天猫", "SKU-34", "STYLE-1", "黑色/34", "TMALL", "690000000001"
    )


def test_vip_daily_sales_mapping_and_key_are_stable():
    mapped = DailySalesRepository._map_vip(
        {"商品ID": 101, "SIZE_ID": 34, "销售量": 5, "销售额": "888.50", "货号": "QBD001"}
    )
    mapped["sales_date"] = date(2026, 7, 18)

    assert mapped["goods_id"] == "101"
    assert mapped["size_id"] == "34"
    assert mapped["sales_quantity"] == 5
    assert DailySalesRepository._vip_key(mapped) == (date(2026, 7, 18), "101", "34")
