"""Exercise phase two HTTP routes against an isolated PostgreSQL schema."""
from datetime import date, timedelta
from types import SimpleNamespace
import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Column, Integer, MetaData, Table, Text, create_engine, text

from api.auth_middleware import required_permission_for_request
from api.routes import stock_phase_two as api
from domain.stock_phase_two import allocate
from domain.size_group_schema import SIZE_GROUPS_TABLE, SIZE_GROUP_ITEMS_TABLE
from storage.stock_alert_tasks import StockAlertTaskRepository
from storage.stock_phase_two import ARRIVALS, BASELINES, _size_from_source


TODAY = date(2026, 11, 25)
BRAND = "cbanner_mens"
LAST_WEEK = "2026-11-16"


def test_vip_display_size_uses_archive_barcode_and_rejects_conflicts():
    sizes = [{"name": "225", "barcode": "225"}, {"name": "230", "barcode": "230"}]
    product = {"barcode_base": "SKU01"}
    assert _size_from_source(sizes, "35", "SKU01225", product, explicit=True) == "225"
    assert _size_from_source(sizes, "230", "SKU01225", product, explicit=True) is None


def test_allocation_rounds_in_size_order_and_keeps_existing_stock():
    sizes = ["36", "37", "38"]
    assert allocate(sizes, {"36": 1, "37": 1, "38": 1}, {"36": 100}, 3) == {"36": 0, "37": 2, "38": 1}
    assert allocate(sizes, {}, {}, 10) is None


@pytest.fixture
def phase_two(monkeypatch):
    url = os.getenv("TEST_STOCK_OVERVIEW_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated PostgreSQL")
    admin = create_engine(url)
    schema = "stock_planning_test_" + uuid4().hex
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    archive = Table("test_archive", MetaData(), Column("id", Integer, primary_key=True), *[
        Column(name, Text) for name in ("sku", "original_sku", "product_name", "color", "color_code",
            "barcode_build_rule", "size_range", "supplier_name", "launch_date", "season_category", "year",
            "upper_material", "category", "deleted_at", "heel_height", "rear_heel_height")])
    repo = SimpleNamespace(engine=engine, product_archive_brands=lambda: [BRAND], _table_for_brand=lambda _: archive)
    app = FastAPI()
    app.include_router(api.router)
    app.state.repository = repo
    decisions = {}
    app.state.stock_operating = SimpleNamespace(decisions=lambda _: decisions)
    app.state.stock_overview_policies = SimpleNamespace(list_rules=lambda _: {})
    app.state.stock_alert_tasks = SimpleNamespace(overview_week=lambda *args: ({}, {1, 3, 99}, {1, 99}))
    monkeypatch.setattr(api, "business_today", lambda: TODAY)
    monkeypatch.setattr(api, "write_operation_log", lambda *args, **kwargs: None)

    @app.middleware("http")
    async def user(request: Request, call_next):
        from starlette.responses import JSONResponse
        from api.routes.auth import user_has_permission
        role = request.headers.get("x-role", "finance")
        department, permissions = {
            "finance": ("财务部", ["product.view"]),
            "manager": ("商品部", ["product.view", "product.manage", "purchase.view", "purchase.manage"]),
            "operating": ("运营部", ["product.view", "product.manage", "purchase.view"]),
            "viewer": ("客服部", ["product.view"]),
        }[role]
        current = {"id": 10, "department_code": department, "role_code": role, "permissions": permissions}
        request.state.current_user = current
        permission = required_permission_for_request(request.method, request.url.path)
        if not user_has_permission(current, permission):
            return JSONResponse({"detail": "权限不足"}, status_code=403)
        return await call_next(request)

    try:
        StockAlertTaskRepository(engine).create_tables()
        archive.create(engine)
        SIZE_GROUPS_TABLE.create(engine)
        SIZE_GROUP_ITEMS_TABLE.create(engine)
        with engine.begin() as conn:
            for sql in (
                """CREATE TABLE jst_full_stock(sync_date date, product_code text, style_code text, size text,
                    available_qty bigint, purchase_in_transit_qty bigint)""",
                """CREATE TABLE jst_daily_sales(sales_date date, product_code text, style_code text, color_spec text,
                    channel text, net_sales_quantity bigint, barcode text)""",
                """CREATE TABLE vip_daily_sales(sales_date date, goods_code text, style_code text,
                    size_name text, sales_quantity bigint, barcode text)""",
                """CREATE TABLE v_jst_purchase_inbound_age_candidates(goods_code text, style_color_code text,
                    inbound_date date, purchase_order_id text, size text, quantity numeric)""",
                """CREATE TABLE product_archive_identities(id bigint primary key, brand text,
                    source_product_id bigint, is_active boolean)""",
                """CREATE TABLE inventory_records(id bigint primary key, document_number text, date_value date,
                    extra_fields json, supplier text, deleted_at timestamp, document_type text)""",
                """CREATE TABLE inventory_details(product_identity_id bigint, document_id bigint,
                    quantity numeric, size_quantities json)""",
                """CREATE TABLE factory_channel_sales_daily_summaries(brand text, match_status text, sales_date date,
                    product_code text, channel_group text, quantity bigint)""",
                "CREATE TABLE jst_size_stock_snapshots(snapshot_date date, product_code text, size text, stock_qty bigint)",
                "INSERT INTO size_groups(id,name) VALUES (1,'测试尺码')",
                "INSERT INTO size_group_items(size_group_id,size_name,barcode) VALUES (1,'36','36'), (1,'37','37')",
            ):
                conn.exec_driver_sql(sql)
            conn.execute(archive.insert(), [{"id": i, "sku": sku, "product_name": "板鞋", "size_range": "测试尺码"}
                                           for i, sku in [(1, "TEST-RED"), (2, "TEST-BLUE"), (3, "NEW")]])
            day = TODAY - timedelta(days=1)
            conn.execute(text("""INSERT INTO jst_full_stock VALUES (:today, 'TEST-RED', '', '36', 12, 8),
                                   (:today, 'TEST-RED', '', '37', 2, 3), (:today, 'NEW', '', '36', 0, 0)"""), {"today": TODAY})
            conn.execute(text("""INSERT INTO jst_daily_sales SELECT day, 'OTHER', '', '', '', 0, ''
                FROM generate_series(CAST(:first AS date), CAST(:end AS date), interval '1 day') d(day)"""),
                {"first": TODAY - timedelta(days=30), "end": day})
            conn.execute(text("""INSERT INTO vip_daily_sales SELECT day, 'OTHER', '', '', 0, ''
                FROM generate_series(CAST(:first AS date), CAST(:end AS date), interval '1 day') d(day)"""),
                {"first": TODAY - timedelta(days=30), "end": day})
            conn.execute(text("""INSERT INTO vip_daily_sales VALUES (:day,'TEST-RED','','36',12,''),
                    (:day,'TEST-RED','','37',8,'')"""), {"day": day})
            conn.execute(text("""INSERT INTO jst_daily_sales VALUES (:day,'TEST-RED','','黑;37','天猫',10,''),
                    (:day,'TEST-RED','','黑;36','唯品会',10,''),(:day,'TEST-RED','','黑;36','拼多多清仓',10,''),
                    (:day,'TEST-RED','','黑;36','京东VMI',10,'')"""), {"day": day})
            conn.execute(text("INSERT INTO product_archive_identities VALUES (101, :brand, 1, true), (102, :brand, 2, true)"), {"brand": BRAND})
            conn.exec_driver_sql("""INSERT INTO inventory_records VALUES
                (51, 'PO-1', '2026-10-01', '{"delivery_date":"2026-10-25"}', '工厂甲', NULL, '进货订单'),
                (52, 'PO-2', '2026-11-20', '{"delivery_date":"2026-11-24"}', '工厂乙', NULL, '进货订单'),
                (53, 'DUP', '2026-11-21', '{"delivery_date":"2026-11-26"}', '工厂乙', NULL, '进货订单'),
                (54, 'DUP', '2026-11-22', '{}', '工厂丙', NULL, '进货订单'),
                (55, 'PO-3', '2026-11-22', '{"delivery_date":"2026-11-26"}', '工厂甲', NULL, '进货订单')""")
            conn.exec_driver_sql("""INSERT INTO inventory_details VALUES (101, 51, 10, '{"36":10}'),
                (101, 52, 16, '{"36":10,"37":6}'), (102, 52, 12, '{"36":12}'),
                (101, 53, 6, '{"36":6}'), (101, 55, 5, '{"36":5}')""")
            conn.exec_driver_sql("""INSERT INTO v_jst_purchase_inbound_age_candidates VALUES
                ('TEST-RED','','2026-10-22','PO-1','36',10),
                ('TEST-RED','','2026-11-23','PO-2','36',2),
                ('TEST-BLUE','','2026-11-23','PO-2','36',1),
                ('TEST-RED','','2026-11-23','PO-3','无法识别',2)""")
            conn.execute(text("""INSERT INTO factory_channel_sales_daily_summaries
                SELECT :brand, 'date_marker', day, '', '', 0 FROM
                generate_series(date '2026-11-16', date '2026-11-22', interval '1 day') d(day)"""), {"brand": BRAND})
            conn.execute(text("""INSERT INTO factory_channel_sales_daily_summaries VALUES
                (:brand, 'matched', '2026-11-22', 'TEST-RED', 'clearance', 3)"""), {"brand": BRAND})
            conn.exec_driver_sql("INSERT INTO jst_size_stock_snapshots VALUES ('2026-11-22','TEST-RED','36',7)")
        with TestClient(app) as client:
            yield client, engine, decisions
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def test_planning_arrivals_campaign_and_confirmed_transit(phase_two):
    client, engine, decisions = phase_two
    client.headers.update({"x-role": "manager"})
    url = "/stock-alerts/planning"
    params = {"brand": BRAND, "total": 20, "need_by": "2026-11-29"}
    baseline = client.put(f"{url}/size-baseline", json={"brand": BRAND, "product_id": 1, "weights": {"36": 1, "37": 2}})
    assert baseline.status_code == 200, baseline.text
    result = client.get(f"{url}/items/3", params=params).json()
    assert result["basis"] == "category" and sum(result["suggested"].values()) == 20
    campaign = client.post(f"{url}/campaigns", json={"brand": BRAND, "name": "大促", "start_date": "2026-11-28",
                                                    "end_date": "2026-11-30", "factor": "2.5"})
    assert campaign.status_code == 200, campaign.text
    params["campaign_id"] = campaign.json()["item"]["id"]
    response = client.get(f"{url}/items/1", params=params)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sales"] == {"36": 12, "37": 18}
    assert result["basis"] == "same_product" and sum(result["suggested"].values()) == 20
    assert result["demand"]["normal"] == 5 and result["demand"]["campaign"] == 8
    orders = {row["id"]: row for row in result["orders"]}
    assert orders[51]["status"] == "received" and orders[51]["kind"] == "首单"
    assert orders[52]["remaining"] == 14 and orders[52]["status"] == "overdue"
    assert orders[55]["status"] == "due_soon" and orders[55]["remaining_sizes"] == {}
    assert orders[53]["remaining"] is None
    body = {"brand": BRAND, "product_id": 1, "order_id": 52, "eta": "2026-11-27",
            "sizes": {"36": 8, "37": 5}, "note": "工厂已确认"}
    assert client.put(f"{url}/arrivals", json=body, headers={"x-role": "operating"}).status_code == 403
    assert client.put(f"{url}/arrivals", json=body | {"order_id": 53}).status_code == 409
    link = {"brand": BRAND, "product_id": 1, "order_id": 52, "external_number": "EXT-52", "note": "已核对"}
    assert client.put(f"{url}/purchase-order-link", json=link | {"external_number": "PO-1"}).status_code == 409
    saved = client.put(f"{url}/arrivals", json=body)
    assert saved.status_code == 200, saved.text
    assert client.get(f"{url}/arrivals", params=params, headers={"x-role": "viewer"}).status_code == 403
    board = client.get(f"{url}/arrivals", params=params).json()
    assert board["total"] == 1 and board["items"][0]["supplier"] == "工厂乙"
    assert client.get(f"{url}/items/1", params=params).json()["eligible_transit"] == {"36": 8, "37": 3}
    with engine.begin() as conn:
        conn.exec_driver_sql("""INSERT INTO v_jst_purchase_inbound_age_candidates VALUES
            ('TEST-RED','','2026-11-25','PO-2','36',3)""")
    viewer = client.get(f"{url}/items/1", params=params, headers={"x-role": "viewer"}).json()
    assert viewer["eligible_transit"] == {"36": 5, "37": 3} and viewer["orders"] is None
    assert client.get(f"{url}/items/1", params=params | {"need_by": "2026-11-26"}).json()["eligible_transit"] == {"36": 0, "37": 0}
    decisions[1] = {"confirmed": True}
    assert client.get(f"{url}/items/1", params=params).json()["suggested"] is None
    with engine.begin() as conn:
        conn.execute(ARRIVALS.update().values(eta=TODAY - timedelta(days=1)))
    assert client.get(f"{url}/arrivals", params=params).json()["total"] == 0
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE v_jst_purchase_inbound_age_candidates SET purchase_order_id='EXT-52' WHERE purchase_order_id='PO-2'")
    unlinked = {row["id"]: row for row in client.get(f"{url}/items/1", params=params).json()["orders"]}
    assert unlinked[52]["remaining"] is None and not unlinked[52]["receipts_verified"]
    linked = client.put(f"{url}/purchase-order-link", json=link)
    assert linked.status_code == 200, linked.text
    current = {row["id"]: row for row in client.get(f"{url}/items/1", params=params).json()["orders"]}
    assert current[52]["remaining"] == 11 and current[52]["confirmation"]["eta"] is None
    assert client.put(f"{url}/purchase-order-link", json=link | {"order_id": 55}).status_code == 409
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM vip_daily_sales WHERE sales_date=:day"), {"day": TODAY - timedelta(days=2)})
    assert client.get(f"{url}/items/3", params=params).json()["suggested"] is None


def test_planning_uses_30_days_through_latest_shared_sales_date(phase_two):
    client, engine, _ = phase_two
    with engine.begin() as conn:
        # Only JST has yesterday's data, and today's partial data must not shift the window.
        conn.execute(text("DELETE FROM vip_daily_sales WHERE sales_date=:day"), {"day": TODAY - timedelta(days=1)})
        for offset, quantity in [(32, 100), (31, 24), (2, 6), (1, 50), (0, 80)]:
            day = TODAY - timedelta(days=offset)
            conn.execute(text("INSERT INTO jst_daily_sales VALUES (:day,'TEST-RED','','黑;36','天猫',:quantity,'')"),
                         {"day": day, "quantity": quantity})
            if offset in (32, 31, 0):
                conn.execute(text("INSERT INTO vip_daily_sales VALUES (:day,'OTHER','','',0,'')"), {"day": day})
    result = client.get("/stock-alerts/planning/items/1", params={"brand": BRAND, "total": 100})
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["sales_start"] == (TODAY - timedelta(days=31)).isoformat()
    assert result["cutoff"] == (TODAY - timedelta(days=2)).isoformat()
    assert result["sales_days"] == 30 and result["sales_complete"]
    assert result["sales"] == {"36": 30}
    assert result["basis"] == "same_product" and sum(result["suggested"].values()) == 100


def test_planning_keeps_season_heel_and_color_references_separate(phase_two):
    client, engine, _ = phase_two
    client.headers.update({"x-role": "manager"})
    prefix = "/stock-alerts/planning"
    with engine.begin() as conn:
        conn.exec_driver_sql("""UPDATE test_archive SET original_sku='STYLE', season_category='春秋',
            color=CASE id WHEN 1 THEN '红' ELSE '蓝' END, rear_heel_height='高跟(6-8cm)' WHERE id IN (1, 2)""")
        conn.exec_driver_sql("""UPDATE test_archive SET season_category='春秋', rear_heel_height='低跟(小于3cm)'
                                WHERE id=3""")
        conn.exec_driver_sql("""INSERT INTO test_archive (id,sku,original_sku,product_name,color,season_category,rear_heel_height,size_range)
            VALUES (4,'PEER','PEER','尖头鞋','黑','春秋','高跟','测试尺码'),
                   (5,'WRONG','STYLE','板鞋','白','春秋','低跟','测试尺码')""")
        conn.execute(text("INSERT INTO jst_full_stock VALUES (:today, 'TEST-BLUE', '', '36', 7, 0)"), {"today": TODAY})
        conn.execute(BASELINES.insert().values(brand=BRAND, category="板鞋", size_group="测试尺码",
                                               weights={"36": 1, "37": 1}, updated_by=10))
    base = {"brand": BRAND, "total": 20, "season": "春"}
    path = f"{prefix}/items/2"
    assert client.get(path, params=base | {"season": "冬"}).status_code == 422

    data = client.get(path, params=base).json()
    assert data["basis"] == "manual" and data["legacy_baseline"] == {"36": 1, "37": 1}
    assert data["allocation_seasons"] == ["春秋", "春", "秋"]
    assert [item["id"] for item in data["other_colors"]] == [1]

    for product_id, weights in [(1, {"36": 2, "37": 1}), (3, {"36": 1, "37": 0}), (4, {"36": 0, "37": 1})]:
        saved = client.put(f"{prefix}/size-baseline", json={"brand": BRAND, "product_id": product_id,
                                                            "season": "春", "weights": weights})
        assert saved.status_code == 200, saved.text
    result = client.get(path, params=base).json()
    assert result["basis"] == "category" and result["weights"] == {"36": 2, "37": 1}
    assert result["related_categories"] == ["尖头鞋"]
    forced = client.get(f"{prefix}/items/1", params=base | {"reference_category": "板鞋"}).json()
    assert forced["basis"] == "category" and forced["weights"] == {"36": 2, "37": 1}
    assert client.get(path, params=base | {"season": "秋"}).json()["suggested"] is None

    peer = client.get(path, params=base | {"reference_category": "尖头鞋"}).json()
    assert peer["basis"] == "related_category" and peer["suggested"] == {"36": 0, "37": 20}
    assert client.get(f"{prefix}/items/3", params=base | {"reference_category": "尖头鞋"}).status_code == 422
    assert client.get(path, params=base | {"reference_product_id": 5}).status_code == 422

    other = client.get(path, params=base | {"reference_product_id": 1}).json()
    assert other["basis"] == "other_color" and other["reference"]["color"] == "红"
    assert other["sales"] == {} and other["weights"] == {"36": 12, "37": 18}
    assert other["reference"]["sales"] == {"36": 12, "37": 18}
    assert other["stock"] == {"36": 7} and sum(other["suggested"].values()) == 20


def test_clearance_keeps_missing_archive_visible_and_amount_exact(phase_two):
    client, _, _ = phase_two
    url = "/stock-alerts/planning/clearance-week"
    params = {"brand": BRAND, "first": LAST_WEEK}
    initial = client.get(url, params=params)
    assert initial.status_code == 200, initial.text
    initial = initial.json()
    assert initial["can_confirm"]
    assert not client.get(url, params=params, headers={"x-role": "viewer"}).json()["can_confirm"]
    assert [(row["product_id"], row["net_sales"], row["ending_stock"]) for row in initial["items"]] == [
        (1, 3, 7), (99, None, None)]
    body = {**params, "product_id": 1, "amount": "99999999999999.99", "reference": "财务单号"}
    assert client.put(f"{url}/recovery", json=body, headers={"x-role": "operating"}).status_code == 403
    assert client.put(f"{url}/recovery", json=body | {"product_id": 3}).status_code == 409
    assert client.put(f"{url}/recovery", json=body).json()["item"]["amount"] == body["amount"]
    assert client.put(f"{url}/recovery", json=body | {"product_id": 99, "amount": "0.01"}).status_code == 200
    result = client.get(url, params=params).json()
    assert result["recovery_amount"] == "100000000000000.00"
    assert result["recovery_covered"] == 2 and result["stock_covered"] == 1

