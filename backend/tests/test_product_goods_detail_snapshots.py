from scripts.import_product_goods_detail_snapshots import _platform_values


def test_platform_values_uses_the_group_header_row():
    headers = {11: "唯品", 12: "天猫", 13: "得物", 21: "唯品", 22: "其他"}
    periods = {11: "日销量", 12: "日销量", 13: "日销量", 21: "周销量", 22: "周销量"}

    assert _platform_values(headers, periods) == {
        "daily": [("唯品", 11), ("天猫", 12), ("得物", 13)],
        "weekly": [("唯品", 21), ("其他", 22)],
    }
