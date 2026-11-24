from datetime import date, datetime, timedelta
from time import perf_counter
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, event

from api.fine_table_cache import clear_fine_table_cache
from api.routes import fine_table
from api.routes.fine_table import _daily_metric_with_original_fallback
from storage.fine_table_vip_sales import VIP_SALES_FACTS


def test_original_sku_compass_metrics_are_available_as_fallback():
    current_daily = {}
    original_daily = {
        ("罗盘", "30d"): {
            "reject_count": "3",
            "reject_rate": "12.50%",
        },
    }

    reject_count = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_count",
    )
    reject_rate = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_rate",
    )

    assert reject_count == "3"
    assert reject_rate == "12.50%"


def test_current_sku_compass_metrics_take_priority():
    current_daily = {
        ("罗盘", "30d"): {
            "reject_count": "0",
            "reject_rate": "0.00%",
        },
    }
    original_daily = {
        ("罗盘", "30d"): {
            "reject_count": "3",
            "reject_rate": "12.50%",
        },
    }

    reject_count = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_count",
    )
    reject_rate = _daily_metric_with_original_fallback(
        current_daily,
        original_daily,
        "30d",
        "reject_rate",
    )

    assert reject_count == "0"
    assert reject_rate == "0.00%"


@pytest.mark.parametrize("brand", ["cbanner_mens", "yandou"])
@pytest.mark.parametrize("sort_by, highest_sales", [("vip_3d_sales", 33), ("original_all_7d_sales", 1514)])
def test_sales_rank_matches_full_results_and_only_hydrates_the_page(brand, sort_by, highest_sales):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    archive = fine_table.PRODUCT_TABLES[brand]
    for source in (
        archive, fine_table.GJ_MERGED_PRODUCT_INFO_TABLE, fine_table.VIP_OPS_TABLE,
        fine_table.VIP_DAILY_TABLE, fine_table.JST_SIZE_STOCK_TABLE, fine_table.JST_STOCK_SUMMARY_TABLE,
        fine_table.JST_PURCHASE_DIFF_TABLE, fine_table.VIP_DAILY_SNAPSHOT_TABLE,
        fine_table.JST_MONTHLY_ORDERS_TABLE, VIP_SALES_FACTS,
        fine_table.PRODUCT_GOODS_OVERRIDES_TABLE, fine_table.SUPPLIER_TABLE,
    ):
        Table(source.name, metadata, *(Column(column.name, column.type) for column in source.c))
    metadata.create_all(engine)
    count = 1200
    page_size = 50
    end_order = datetime(2026, 11, 22, 16)
    end_vip = date(2026, 11, 21)
    candidate_codes = [f"SALE-{index:04d}" for index in range(count)]
    originals = [f"OLD-{index // 2:04d}" for index in range(count)]
    archive_rows = [
        {"id": index + 1, "sku": sku, "original_sku": original, "raw_payload": {"text": "x" * 1000}}
        for index, (sku, original) in enumerate(zip(candidate_codes, originals))
    ]
    archive_rows.extend([
        {"id": count + 1, "sku": "ALIAS", "original_sku": originals[0], "raw_payload": {}},
        {"id": count + 2, "sku": "ARCHIVED", "original_sku": originals[0], "raw_payload": {}},
    ])
    facts = [
        {"goods_code": sku, "sales_date": end_vip - timedelta(days=offset), "brand_name": None, "sales_quantity": index % 12}
        for index, sku in enumerate(candidate_codes)
        for offset in range(30)
    ]
    facts.extend([
        {"goods_code": "ALIAS", "sales_date": end_vip, "brand_name": None, "sales_quantity": 900},
        {"goods_code": "ALIAS", "sales_date": end_vip, "brand_name": "FOREIGN", "sales_quantity": 4000},
        {"goods_code": "ARCHIVED", "sales_date": end_vip, "brand_name": None, "sales_quantity": 5000},
    ])
    order_rows = [
        {"style_code": sku, "order_time_at": end_order - timedelta(days=offset), "status": None, "shop_name": None, "quantity": index % 9}
        for index, sku in enumerate(candidate_codes)
        for offset in range(30)
    ]
    order_rows.extend([
        {"style_code": "ALIAS", "order_time_at": end_order, "status": " \u53d6\u6d88 ", "shop_name": None, "quantity": 7000},
        {"style_code": "ALIAS", "order_time_at": end_order, "status": None, "shop_name": "\u552f\u54c1\u4f1a", "quantity": 8000},
        {"style_code": "ALIAS", "order_time_at": end_order, "status": None, "shop_name": None, "quantity": 600},
    ])
    with engine.begin() as connection:
        connection.execute(metadata.tables[archive.name].insert(), archive_rows)
        connection.execute(metadata.tables[archive.name].update().where(metadata.tables[archive.name].c.sku == "ARCHIVED").values(deleted_at=end_order))
        connection.execute(metadata.tables[VIP_SALES_FACTS.name].insert(), facts)
        connection.execute(metadata.tables[fine_table.JST_MONTHLY_ORDERS_TABLE.name].insert(), order_rows)
        if brand == "cbanner_mens":
            connection.execute(metadata.tables[fine_table.GJ_MERGED_PRODUCT_INFO_TABLE.name].insert(), [
                {"id": index + 1, "goods_code": sku, "original_goods_code": original,
                 "fine_table_brand": brand, "source_date_value": end_order.date()}
                for index, (sku, original) in enumerate(zip(candidate_codes, originals))
            ])

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repository=SimpleNamespace(engine=engine), settings=SimpleNamespace(image_roots={}),
    )))
    calls = []

    @event.listens_for(engine, "before_cursor_execute")
    def track_queries(connection, cursor, statement, parameters, context, executemany):
        calls.append((statement, parameters))

    def load(**options):
        return fine_table.list_fine_table(
            request, brand=brand, sku_prefix="SALE-", sort_by=sort_by,
            page_size=page_size, **options,
        )

    clear_fine_table_cache()
    try:
        timings = {}
        start = perf_counter()
        full = load(page=1, include_all=True)
        timings["full"] = perf_counter() - start
        clear_fine_table_cache()
        calls.clear()
        start = perf_counter()
        first = load(page=1)
        timings["ranked"] = perf_counter() - start
        assert first["total"] == full["total"] == count
        assert first["items"] == full["items"][:page_size]
        assert first["items"][0][sort_by] == highest_sales
        stock_calls = [params for sql, params in calls if f"FROM {fine_table.JST_SIZE_STOCK_TABLE.name}" in sql]
        assert len(stock_calls) == 1 and len(stock_calls[0]) <= 2 * page_size + 1
        assert ("ALIAS" in stock_calls[0]) == (sort_by == "original_all_7d_sales")
        assert "ARCHIVED" not in stock_calls[0]
        ranking_orders = [sql for sql, _ in calls if "GROUP BY" in sql and "jst_monthly_orders.style_code, jst_monthly_orders.status" in sql]
        assert len(ranking_orders) == int(sort_by == "original_all_7d_sales")
        calls.clear()
        assert load(page=2)["items"] == full["items"][page_size:2 * page_size]
        assert not any("GROUP BY" in sql and "jst_monthly_orders.style_code, jst_monthly_orders.status" in sql for sql, _ in calls)
        ascending = sorted(full["items"], key=lambda row: (row[sort_by], -abs(row["id"])))
        assert load(page=1, sort_direction="asc")["items"] == ascending[:page_size]
        print(f"{brand} {sort_by}: full {timings['full']:.4f}s, ranked {timings['ranked']:.4f}s")
    finally:
        clear_fine_table_cache()
        engine.dispose()
