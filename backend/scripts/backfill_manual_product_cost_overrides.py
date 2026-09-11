"""Mark previously edited product archive costs as manually maintained."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from sqlalchemy import create_engine, select, update

from config import load_settings
from domain.operation_log_schema import OPERATION_LOG_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from storage.product_repository import ProductRepository, _normalize_code


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def backfill(database_url: str) -> int:
    engine = create_engine(database_url, future=True)
    repository = ProductRepository(database_url)
    candidates: dict[tuple[str, int], Decimal] = {}

    with engine.connect() as connection:
        logs = connection.execute(
            select(
                OPERATION_LOG_TABLE.c.before_data,
                OPERATION_LOG_TABLE.c.after_data,
            )
            .where(OPERATION_LOG_TABLE.c.module == "product")
            .where(OPERATION_LOG_TABLE.c.action == "update")
        ).mappings()
        for log in logs:
            before = log["before_data"] if isinstance(log["before_data"], Mapping) else {}
            after = log["after_data"] if isinstance(log["after_data"], Mapping) else {}
            before_cost = _decimal(before.get("cost"))
            after_cost = _decimal(after.get("cost"))
            if after_cost is None or before_cost == after_cost:
                continue
            brand = _normalize_code(after.get("brand"))
            product_id = after.get("id")
            if not brand or not product_id:
                continue
            try:
                candidates[(brand, int(product_id))] = after_cost
            except (TypeError, ValueError):
                continue

    updated = 0
    with engine.begin() as connection:
        for (brand, product_id), saved_cost in candidates.items():
            if not repository.is_product_archive_brand(brand):
                continue
            table = repository._table_for_brand(brand)
            statement = (
                update(table)
                .where(table.c.id == product_id)
                .where(table.c.cost == saved_cost)
                .where(table.c.cost_manual_override.is_(False))
                .values(cost_manual_override=True)
            )
            result = connection.execute(statement)
            updated += result.rowcount or 0

    engine.dispose()
    repository.engine.dispose()
    return updated


def main() -> int:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    updated = backfill(settings.database_url)
    print(f"Marked {updated} historical product costs as manual overrides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
