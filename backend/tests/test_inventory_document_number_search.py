from __future__ import annotations

from sqlalchemy import create_engine, event

from domain.inventory_schema import INVENTORY_TABLE
from storage.inventory_repository import InventoryRepository


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
