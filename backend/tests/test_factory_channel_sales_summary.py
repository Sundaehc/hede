from datetime import date

from domain.factory_channel_sales import sales_metrics
from storage.factory_channel_sales_summary_repository import summarize_factory_channel_sales


def test_sales_metrics_keeps_gross_returns_and_net_separate():
    assert sales_metrics({"quantity": -1, "gross_quantity": 1, "return_quantity": 2}) == (
        -1,
        1,
        2,
    )


def test_factory_channel_summary_groups_channels_and_avoids_duplicate_vip_sales():
    sales_date = date(2026, 8, 20)
    rows = summarize_factory_channel_sales(
        product_rows_by_brand={
            "cbanner_mens": [
                {"sku": "MEN001", "original_sku": "STYLE-M"},
                {"sku": "MEN002", "original_sku": "STYLE-M2"},
            ],
        },
        shop_channel_mappings_by_brand={
            "cbanner_mens": {
                "旗舰店": "直播赛道",
                "清仓店": "拼多多清仓",
            },
        },
        vip_rows=[
            {"sales_date": sales_date, "product_code": "MEN001", "style_code": "STYLE-M", "quantity": 3},
        ],
        jst_rows=[
            {"sales_date": sales_date, "product_code": "MEN00134", "style_code": "STYLE-M", "channel": "唯品会", "quantity": 3},
            {"sales_date": sales_date, "product_code": "MEN00134", "style_code": "STYLE-M", "channel": "旗舰店", "quantity": 2},
            {"sales_date": sales_date, "product_code": "MEN00235", "style_code": "STYLE-M2", "channel": "清仓店", "quantity": 4},
            {"sales_date": sales_date, "product_code": "UNKNOWN", "style_code": "", "channel": "天猫", "quantity": 5},
        ],
    )

    keyed = {
        (row["product_code"], row["channel_group"], row["match_status"]): row["quantity"]
        for row in rows
    }
    assert keyed[("MEN001", "traditional", "matched")] == 3
    assert keyed[("MEN001", "traditional", "duplicate_vip")] == 3
    assert keyed[("MEN001", "live", "matched")] == 2
    assert keyed[("MEN002", "clearance", "matched")] == 4
    assert keyed[("", "traditional", "unmatched")] == 5
    assert keyed[("", "", "date_marker")] == 0


def test_factory_channel_summary_does_not_use_negative_net_as_display_sales():
    rows = summarize_factory_channel_sales(
        product_rows_by_brand={"cbanner_mens": [{"sku": "MEN001", "original_sku": "STYLE-M"}]},
        shop_channel_mappings_by_brand={"cbanner_mens": {"直播店": "直播赛道"}},
        vip_rows=[],
        jst_rows=[
            {
                "sales_date": date(2026, 8, 20),
                "product_code": "MEN00134",
                "style_code": "STYLE-M",
                "channel": "直播店",
                "quantity": -1,
                "gross_quantity": 1,
                "return_quantity": 2,
            }
        ],
    )

    row = next(item for item in rows if item["match_status"] == "matched")
    assert row["quantity"] == -1
    assert row["gross_quantity"] == 1
    assert row["return_quantity"] == 2
