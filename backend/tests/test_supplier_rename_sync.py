from __future__ import annotations

from sqlalchemy import insert, select

from domain.inventory_schema import INVENTORY_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.inventory_repository import InventoryRepository


def test_supplier_rename_syncs_product_archive_and_supplier_documents(
    test_database_url: str,
    recreate_tables,
) -> None:
    repository = InventoryRepository(test_database_url)
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
    assert updated["name"] == new_name
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
