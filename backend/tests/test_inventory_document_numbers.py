from __future__ import annotations

from sqlalchemy import update

from domain.inventory_schema import INVENTORY_TABLE
from storage.inventory_repository import InventoryRepository


def test_backfill_document_numbers_only_fills_empty_numbers_without_renumbering(test_database_url: str, recreate_tables) -> None:
    repository = InventoryRepository(test_database_url)
    existing = repository.create_record({
        "date": "2026-08-03",
        "document_type": "进货退货单",
        "document_number": "JHTHD-2026-08-03-0008",
    })
    missing = repository.create_record({
        "date": "2026-08-03",
        "document_type": "进货退货单",
    })
    with repository.engine.begin() as connection:
        connection.execute(
            update(INVENTORY_TABLE)
            .where(INVENTORY_TABLE.c.id == missing["id"])
            .values(document_number=None)
        )
        InventoryRepository._backfill_document_numbers(connection)

    assert repository.get_record(existing["id"])["document_number"] == "JHTHD-2026-08-03-0008"
    assert repository.get_record(missing["id"])["document_number"] == "JHTHD-2026-08-03-0001"
