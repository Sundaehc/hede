from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select, update

from api.routes import suppliers as supplier_routes

from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.supplier_change_schema import SUPPLIER_CHANGE_TABLE, SupplierNameExists
from storage.inventory_repository import InventoryRepository


def test_super_admin_outside_product_department_can_list_and_review_supplier_changes():
    admin = {"id": 10, "role_code": "super_admin", "department_code": "开发部", "permissions": ["*"]}
    application = FastAPI()
    repository = Mock()
    repository.list_supplier_changes.return_value = {"items": [], "total": 0, "page_size": 20}
    repository.review_supplier_change.return_value = {
        "review": {"before": {"name": "供应商", "brand": "ni", "factory_code": ""}, "proposed": {}, "status": "approved"},
    }
    application.state.inventory_repository = repository
    application.include_router(supplier_routes.router)
    with (
        patch.object(supplier_routes, "actor_from_request", return_value=admin),
        patch.object(supplier_routes, "_record_supplier_update", return_value=({}, "供应商已更新")),
        TestClient(application) as client,
    ):
        assert client.get("/suppliers/change-requests").json()["can_review"] is True
        repository.list_supplier_changes.assert_called_once_with(page=1, status="pending", requester_id=None)
        response = client.put("/suppliers/change-requests/1", json={"decision": "approve"})
        assert response.status_code == 200
        assert response.json()["review"]["status"] == "approved"


def test_supplier_rename_syncs_product_archive_and_supplier_documents(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = object.__new__(InventoryRepository)
    repository.engine = create_engine(test_database_url)
    old_name = "供应商更名前"
    new_name = "供应商更名后"
    supplier = repository.create_supplier({
        "brand": "cbanner_mens",
        "name": old_name,
    })
    product_table = PRODUCT_ARCHIVE_TABLES["cbanner_mens"]
    with repository.engine.begin() as connection:
        connection.execute(insert(product_table).values(
            source_workbook="supplier-rename-test.xlsx",
            source_sheet="商品信息",
            source_row_number="2",
            raw_payload={},
            sku="SUPPLIER-RENAME-001",
            supplier_name=old_name,
        ))

    purchase_order = repository.create_record({
        "date": "2026-08-20",
        "supplier": old_name,
        "warehouse": "测试仓库",
        "document_type": "进货订单",
        "summary": "供应商更名采购单",
    })
    payable = repository.create_record({
        "date": "2026-08-20",
        "supplier": old_name,
        "document_type": "应付款增加",
        "summary": "供应商更名应付款",
    })
    wholesale_sale = repository.create_record({
        "date": "2026-08-20",
        "supplier": old_name,
        "warehouse": "测试仓库",
        "document_type": "批发销售单",
        "summary": "同名客户不能被供应商更名影响",
    })
    partial_match = repository.create_record({
        "date": "2026-08-20",
        "supplier": f"{old_name}-分厂",
        "warehouse": "测试仓库",
        "document_type": "进货单",
        "summary": "供应商部分名称不能被修改",
    })

    updated = repository.update_supplier(int(supplier["id"]), {
        **supplier,
        "name": new_name,
    })

    assert updated is not None
    assert updated["item"]["name"] == new_name
    with repository.engine.connect() as connection:
        product_supplier = connection.execute(
            select(product_table.c.supplier_name)
            .where(product_table.c.sku == "SUPPLIER-RENAME-001")
        ).scalar_one()
        document_suppliers = dict(connection.execute(
            select(INVENTORY_TABLE.c.id, INVENTORY_TABLE.c.supplier)
            .where(INVENTORY_TABLE.c.id.in_({
                purchase_order["id"],
                payable["id"],
                wholesale_sale["id"],
                partial_match["id"],
            }))
        ).all())

    assert product_supplier == new_name
    assert document_suppliers[purchase_order["id"]] == new_name
    assert document_suppliers[payable["id"]] == new_name
    assert document_suppliers[wholesale_sale["id"]] == old_name
    assert document_suppliers[partial_match["id"]] == f"{old_name}-分厂"


def test_supplier_with_expenses_requires_independent_product_team_review(test_database_url, recreate_tables):
    repository = object.__new__(InventoryRepository)
    repository.engine = create_engine(test_database_url)
    womens = "鞋密码（千百度女鞋）"
    hejin = "鞋密码（千百度赫锦）"
    with repository.engine.begin() as connection:
        connection.execute(insert(SUPPLIER_BRAND_TABLE), [
            {"code": "cbanner_womens", "name": "千百度女鞋"},
            {"code": "hejin", "name": "千百度赫锦"},
        ])
    original = repository.create_supplier({"name": womens, "brand": "cbanner_womens"})
    # The second entry predates the global name check.
    with repository.engine.begin() as connection:
        duplicate = connection.execute(insert(SUPPLIER_TABLE).values(name=womens, brand="hejin")
                                       .returning(SUPPLIER_TABLE)).mappings().one()
    with repository.engine.begin() as connection:
        repository._ensure_supplier_schema(connection)
    assert repository.get_supplier(duplicate["id"])["brand"] == "hejin"
    assert repository.get_supplier(original["id"])["brand"] == "cbanner_womens"
    assert repository.update_supplier(duplicate["id"], {"notes": "历史档案"})["item"]["notes"] == "历史档案"
    repository.update_supplier(duplicate["id"], {"notes": None})
    receipt = repository.create_record({"date": "2026-05-10", "supplier": womens,
                                        "document_type": "进货单", "warehouse": "女鞋仓", "amount": 0})
    with repository.engine.begin() as connection:
        connection.execute(insert(INVENTORY_TABLE).values(
            date="2026-05-11", supplier=womens, document_type="应付款减少", amount=80,
        ))
        connection.execute(insert(INVENTORY_DETAIL_TABLE).values(document_id=receipt["id"], amount=80))
    no_fees = repository.create_supplier({"name": "新供应商", "brand": "cbanner_womens"})
    for kind, amount in (("进货订单", 100), ("进货单", 0), ("批发销售单", 100)):
        with repository.engine.begin() as connection:
            connection.execute(insert(INVENTORY_TABLE).values(date="2026-11-10", supplier=no_fees["name"],
                                                              document_type=kind, amount=amount))
    app = FastAPI()
    app.state.inventory_repository = repository
    app.include_router(supplier_routes.router)
    accounts = {
        "finance": {"id": 10, "username": "Finance", "department_code": "财务部", "permissions": ["supplier.manage"]},
        "product": {"id": 20, "username": "Product", "department_code": "商品部", "permissions": ["supplier.manage"]},
        "other-product": {"id": 21, "username": "Product 2", "department_code": "商品组", "permissions": ["supplier.manage"]},
        "readonly": {"id": 30, "username": "Read", "department_code": "商品部", "permissions": ["inventory.view"]},
    }

    @app.middleware("http")
    async def identify(request: Request, next_handler):
        request.state.current_user = accounts.get(request.headers.get("test-account"))
        return await next_handler(request)

    supplier_url = f"/suppliers/{duplicate['id']}"
    queue = "/suppliers/change-requests"
    payload = {"name": hejin, "brand": "hejin", "factory_code": "QJ-A2"}
    def headers(name):
        return {"test-account": name}
    with TestClient(app) as client:
        assert client.put(supplier_url, json=payload).status_code == 409
        submitted = client.put(supplier_url, json=payload, headers=headers("finance")).json()["review"]
        assert submitted["status"] == "pending" and submitted["expense_document_count"] == 2
        assert repository.get_supplier(duplicate["id"])["name"] == womens
        assert client.put(supplier_url, json=payload, headers=headers("finance")).status_code == 409
        assert client.delete(supplier_url, headers=headers("finance")).status_code == 409
        assert client.get(queue, headers=headers("readonly")).status_code == 403
        assert client.get(queue, headers=headers("finance")).json()["items"][0]["id"] == submitted["id"]
        decision_url = f"{queue}/{submitted['id']}"
        assert client.put(decision_url, json={"decision": "approve"}, headers=headers("finance")).status_code == 403
        assert client.put(decision_url, json={"decision": "reject"}, headers=headers("product")).status_code == 400
        declined = client.put(decision_url, json={"decision": "reject", "note": "wrong brand"}, headers=headers("product"))
        assert declined.json()["review"]["status"] == "rejected"
        assert repository.get_supplier(duplicate["id"])["name"] == womens

        next_review = client.put(supplier_url, json=payload, headers=headers("product")).json()["review"]
        next_url = f"{queue}/{next_review['id']}"
        assert client.get(queue, headers=headers("finance")).json()["items"] == []
        assert client.get(queue, headers=headers("other-product")).json()["items"][0]["id"] == next_review["id"]
        with repository.engine.begin() as connection:
            connection.execute(update(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == duplicate["id"]).values(notes="intervening update"))
        assert client.put(next_url, json={"decision": "approve"}, headers=headers("other-product")).status_code == 409
        with repository.engine.begin() as connection:
            connection.execute(update(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == duplicate["id"]).values(notes=None))
        occupied = repository.create_supplier({"name": hejin, "brand": "cbanner_womens"})
        conflict = client.put(next_url, json={"decision": "approve"}, headers=headers("other-product"))
        assert conflict.status_code == 409
        assert "已存在" in conflict.json()["detail"]
        assert repository.get_supplier(duplicate["id"])["name"] == womens
        with repository.engine.connect() as connection:
            requests = SUPPLIER_CHANGE_TABLE
            assert connection.execute(select(requests.c.status).where(requests.c.id == next_review["id"])).scalar_one() == "pending"
        assert repository.delete_supplier(occupied["id"])
        approved = client.put(next_url, json={"decision": "approve"}, headers=headers("product"))
        assert approved.status_code == 200
        assert approved.json()["review"]["status"] == "approved"
        assert approved.json()["review"]["reviewer_name"] == "Product"
        assert client.put(next_url, json={"decision": "approve"}, headers=headers("other-product")).status_code == 409
        assert repository.get_supplier(duplicate["id"])["name"] == hejin
        assert repository.get_supplier(original["id"])["name"] == womens
        assert repository.get_record(receipt["id"])["supplier"] == womens
        assert client.delete(supplier_url, headers=headers("finance")).status_code == 409
        follow_up = client.put(supplier_url, json={**payload, "factory_code": "QJ-A3"}, headers=headers("finance"))
        assert follow_up.json()["review"]["status"] == "pending"
        assert repository.get_supplier(duplicate["id"])["factory_code"] == "QJ-A2"
        assert client.delete(f"/suppliers/{original['id']}", headers=headers("finance")).status_code == 409
        direct = client.put(f"/suppliers/{no_fees['id']}", json={**no_fees, "created_at": None, "updated_at": None, "factory_code": "NEW"}, headers=headers("finance"))
        assert direct.json()["item"]["factory_code"] == "NEW"



def test_supplier_full_names_are_unique_across_brands(test_database_url, recreate_tables):
    repository = object.__new__(InventoryRepository)
    repository.engine = create_engine(test_database_url)
    womens = "鞋密码（千百度女鞋）"
    with repository.engine.begin() as connection:
        connection.execute(insert(SUPPLIER_BRAND_TABLE), [
            {"code": "cbanner_womens", "name": "千百度女鞋"},
            {"code": "hejin", "name": "千百度赫锦"},
            {"code": "eblan_womens", "name": "伊伴女鞋"},
        ])

    app = FastAPI()
    app.state.inventory_repository = repository
    app.include_router(supplier_routes.router)
    with TestClient(app) as client:
        first = client.post("/suppliers", json={"name": womens, "brand": "cbanner_womens"})
        assert first.status_code == 200
        for brand, name in [("cbanner_womens", womens), ("hejin", womens), ("eblan_womens", " 鞋密码(千百度女鞋) ")]:
            duplicate = client.post("/suppliers?confirm_cross_brand_code=true", json={"name": name, "brand": brand})
            assert duplicate.status_code == 400
            assert "已存在" in duplicate.json()["detail"]

        for brand, name in [("hejin", "鞋密码（千百度赫锦）"), ("eblan_womens", "鞋密码（伊伴女鞋）")]:
            other = client.post("/suppliers", json={"name": name, "brand": brand})
            assert other.status_code == 200
            assert other.json()["item"]["brand"] == brand
            supplier_id = other.json()["item"]["id"]
            rename = client.put(f"/suppliers/{supplier_id}", json={"name": womens, "brand": brand})
            assert rename.status_code == 409
            assert "已存在" in rename.json()["detail"]
            assert repository.get_supplier(supplier_id)["name"] == name

    with repository.engine.begin() as connection:
        connection.execute(insert(GJ_MERGED_PRODUCT_INFO_TABLE), [
            {"source_date": "2026-11-24", "goods_code": "SYNC-1", "fine_table_brand": "smiley",
             "primary_supplier": "鞋密码(千百度女鞋)"},
            {"source_date": "2026-11-24", "goods_code": "SYNC-2", "fine_table_brand": "smiley",
             "primary_supplier": "同步供应商"},
            {"source_date": "2026-11-24", "goods_code": "SYNC-3", "fine_table_brand": "eblan",
             "primary_supplier": "同步供应商"},
        ])
        assert repository._sync_suppliers_from_gj(connection) == 1
        assert connection.execute(select(SUPPLIER_TABLE.c.name).where(
            SUPPLIER_TABLE.c.name.in_(("同步供应商", "鞋密码(千百度女鞋)")),
        )).scalars().all() == ["同步供应商"]

    barrier = Barrier(2, timeout=5)

    def create_concurrently(brand, name):
        barrier.wait()
        try:
            repository.create_supplier({"name": name, "brand": brand})
        except SupplierNameExists:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create_concurrently, "cbanner_womens", "AB（鞋业）")
        second = pool.submit(create_concurrently, "hejin", " ab(鞋业) ")
        assert sorted([first.result(), second.result()]) == [False, True]
