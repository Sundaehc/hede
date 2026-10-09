from __future__ import annotations

from sqlalchemy import create_engine, event

from domain.inventory_schema import GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE, INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE
from storage.inventory_repository import InventoryRepository


def test_list_records_returns_page_and_all_totals_with_positive_purchase_returns():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    INVENTORY_TABLE.create(engine)
    with engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": 1, "date": "2026-10-01", "document_number": "JHD-1", "document_type": "进货单", "total_count": 3, "amount": 30},
            {"id": 2, "date": "2026-10-02", "document_number": "JHTHD-1", "document_type": "进货退货单", "total_count": -2, "amount": -20},
            {"id": 3, "date": "2026-10-03", "document_number": "JHD-2", "document_type": "进货单", "total_count": 4, "amount": 40},
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    try:
        result = repository.list_records(page=1, page_size=2)
        assert [(item["total_count"], item["amount"]) for item in result["items"]] == [(4, 40), (2, 20)]
        assert result["totals"] == {
            "current_page": {"total_count": "6", "amount": "60"},
            "all": {"total_count": "9", "amount": "90"},
        }
    finally:
        engine.dispose()


def test_list_records_filters_document_number_by_partial_case_insensitive_match():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    INVENTORY_TABLE.create(engine)
    with engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": 1, "date": "2026-10-01", "document_number": "JHD-2026-0001", "document_type": "进货单"},
            {"id": 2, "date": "2026-10-01", "document_number": "PFXSD-2026-0002", "document_type": "批发销售单"},
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    try:
        result = repository.list_records(document_number=" jhd-2026 ", page=1, page_size=20)
        assert result["total"] == 1
        assert [item["document_number"] for item in result["items"]] == ["JHD-2026-0001"]
    finally:
        engine.dispose()


def test_list_records_supports_brand_and_multiple_filter_values():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    INVENTORY_TABLE.create(engine)
    WAREHOUSE_TABLE.create(engine)
    SUPPLIER_BRAND_TABLE.create(engine)
    SUPPLIER_TABLE.create(engine)
    GENERAL_CUSTOMER_SHOP_TABLE.create(engine)
    GENERAL_CUSTOMER_UNIT_TABLE.create(engine)
    with engine.begin() as connection:
        connection.execute(WAREHOUSE_TABLE.insert(), [
            {"id": 1, "brand": "Brand-A", "name": "Warehouse-A1"},
            {"id": 2, "brand": "Brand-A", "name": "Warehouse-A2"},
            {"id": 3, "brand": "Brand-B", "name": "Warehouse-B1"},
        ])
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": 1, "date": "2026-10-01", "document_number": "DOC-1", "document_type": "TYPE-A", "supplier": "Supplier-1", "warehouse": "Warehouse-A1"},
            {"id": 2, "date": "2026-10-02", "document_number": "DOC-2", "document_type": "TYPE-B", "supplier": "Supplier-2", "warehouse": "Warehouse-A2"},
            {"id": 3, "date": "2026-10-03", "document_number": "DOC-3", "document_type": "TYPE-A", "supplier": "Supplier-1", "warehouse": "Warehouse-B1"},
            {"id": 4, "date": "2026-10-04", "document_number": "DOC-4", "document_type": "TYPE-C", "supplier": "Supplier-3", "warehouse": "Warehouse-A1"},
        ])
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    repository.purge_expired_deleted_records = lambda: 0
    try:
        brand_result = repository.list_records(brands=["Brand-A"], page=1, page_size=20)
        assert {item["document_number"] for item in brand_result["items"]} == {"DOC-1", "DOC-2", "DOC-4"}

        combined_result = repository.list_records(
            brands=["Brand-A", "Brand-B"],
            warehouses=["Warehouse-A2", "Warehouse-B1"],
            document_types=["TYPE-A", "TYPE-B"],
            suppliers=["Supplier-1", "Supplier-2"],
            page=1,
            page_size=20,
        )
        assert [item["document_number"] for item in combined_result["items"]] == ["DOC-3", "DOC-2"]
    finally:
        engine.dispose()
