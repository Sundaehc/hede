"""Run only with an isolated PostgreSQL URL."""
from datetime import date, timedelta
from uuid import uuid4
import os

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, Text, create_engine, text

from storage.stock_portfolio_detail import load_portfolio_detail


def test_original_code_detail_uses_inventory_once_and_keeps_sales_windows_and_purchase_permissions():
    url = os.getenv("TEST_STOCK_OVERVIEW_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated PostgreSQL")
    admin = create_engine(url)
    schema = "stock_portfolio_test_" + uuid4().hex
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    brand = "cbanner_mens"
    today = date(2026, 11, 25)
    archive = Table("test_archive", MetaData(), Column("id", Integer, primary_key=True), *[
        Column(name, Text) for name in ("sku", "original_sku", "product_name", "color", "color_code",
            "barcode_build_rule", "size_range", "supplier_name", "launch_date", "season_category", "year",
            "upper_material", "category", "deleted_at")])

    class Repository:
        def __init__(self):
            self.engine = engine

        def product_archive_brands(self):
            return [brand]

        def _table_for_brand(self, _):
            return archive

    try:
        archive.create(engine)
        with engine.begin() as conn:
            conn.execute(archive.insert(), [
                {"id": 1, "sku": "OLD", "original_sku": "OLD"},
                {"id": 2, "sku": "NEW", "original_sku": "old"},
                {"id": 3, "sku": "ABSENT", "original_sku": "old"},
            ])
            for sql in (
                """CREATE TABLE jst_full_stock(sync_date date, product_code text, style_code text, size text,
                    warehouse_name text, available_qty bigint, purchase_in_transit_qty bigint)""",
                """CREATE TABLE jst_daily_sales(sales_date date, product_code text, style_code text, channel text,
                    sales_quantity bigint, return_quantity bigint, net_sales_quantity bigint)""",
                "CREATE TABLE vip_daily_sales(sales_date date, goods_code text, style_code text, sales_quantity bigint)",
                """CREATE TABLE mv_jst_purchase_inbound_age_reference(goods_code text, style_color_code text,
                      original_sku text, first_inbound_date date, last_inbound_date date, received_quantity numeric)""",
                """CREATE TABLE v_jst_purchase_inbound_age_candidates(goods_code text, style_color_code text,
                      original_sku text, inbound_date date, inbound_id text, purchase_order_id text, quantity numeric)""",
                """CREATE TABLE product_archive_identities(id bigint primary key, brand text,
                    source_product_id bigint, is_active boolean)""",
                """CREATE TABLE inventory_records(id bigint primary key, document_number text, date_value date,
                      extra_fields json, deleted_at timestamp, document_type text)""",
                "CREATE TABLE inventory_details(product_identity_id bigint, document_id bigint, quantity numeric)",
            ):
                conn.exec_driver_sql(sql)
            conn.execute(text("""INSERT INTO jst_full_stock VALUES (:today, 'OLD', 'OLD', '38', 'A', 6, 0),
                (:today, 'OLD', 'OLD', '38', 'B', 2, 0), (:today, 'NEW', 'OLD', '38', 'A', 11, 5)"""), {"today": today})
            yesterday = today - timedelta(days=1)
            for offset in range(30):
                day = yesterday - timedelta(days=offset)
                conn.execute(text("INSERT INTO jst_daily_sales VALUES (:day, 'OTHER', '', '', 0, 0, 0)"), {"day": day})
                if offset != 12:
                    conn.execute(text("INSERT INTO vip_daily_sales VALUES (:day, 'OTHER', '', 0)"), {"day": day})
            conn.execute(text("""INSERT INTO jst_daily_sales VALUES (:day, 'OLD', 'OLD', '千百度京东自营', 7, 1, 6),
                (:day, 'OLD', 'OLD', '千百度京东自营VMI', 7, 1, 6), (:day, 'NEW', 'OLD', '千百度-唯品会', 2, 0, 2)"""), {"day": yesterday})
            conn.execute(text("INSERT INTO vip_daily_sales VALUES (:day, 'NEW', 'OLD', 5)"), {"day": yesterday})
            conn.execute(text("""INSERT INTO mv_jst_purchase_inbound_age_reference VALUES
                ('OLD', 'OLD', 'OLD', :day, :day, 10), ('NEW', 'OLD', 'OLD', :day, :day, 22)"""), {"day": yesterday})
            conn.execute(text("""INSERT INTO v_jst_purchase_inbound_age_candidates VALUES
                ('OLD', 'OLD', 'OLD', :day, 'IN-1', 'PO-1', 10)"""), {"day": yesterday})
            conn.execute(text("INSERT INTO product_archive_identities VALUES (101, :brand, 1, true)"), {"brand": brand})
            conn.execute(text("""INSERT INTO inventory_records VALUES
                (55, 'PO-1', :day, CAST(:extra AS json), NULL, '进货订单')"""),
                {"day": yesterday, "extra": '{"delivery_date":"2026-11-27"}'})
            conn.execute(text("INSERT INTO inventory_details VALUES (101, 55, 12)"))
        repo = Repository()
        detail = load_portfolio_detail(repo, brand, 2, {2: {"confirmed": True}},
                                       can_view_inventory=False, can_view_purchases=False, today=today)
        children = {row["id"]: row for row in detail["items"]}
        assert [children[i]["available_quantity"] for i in (1, 2, 3)] == [8, 11, None]
        assert children[2]["clearance"] == {"confirmed": True}
        assert children[1]["stock"] == [{"size": "38", "warehouse": "A", "available": 6, "transit": 0},
                                       {"size": "38", "warehouse": "B", "available": 2, "transit": 0}]
        assert detail["orders"] is None and detail["receipts"]["recent"] is None
        assert detail["receipts"]["by_product"][2]["quantity"] == 22
        sales = {row["platform"]: row for row in detail["sales"]["channels"]}
        assert sales["京东"]["windows"][1] == {"gross": 7, "returns": 1, "net": 6}
        assert sales["唯品"]["windows"][7] == {"gross": 5, "returns": None, "net": 5}
        assert sales["唯品"]["windows"][15] is None
        permitted = load_portfolio_detail(repo, brand, 1, {}, can_view_inventory=True,
                                          can_view_purchases=True, today=today)
        assert permitted["orders"][0]["id"] == 55
        assert permitted["orders"][0]["delivery_date"] == date(2026, 11, 27)
        assert permitted["receipts"]["recent"][0]["inbound_id"] == "IN-1"
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()

