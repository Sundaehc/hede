"""Add performance indexes to existing databases.

Run: python -m scripts.add_performance_indexes
"""
from __future__ import annotations

from config import load_settings
from sqlalchemy import create_engine, text


def main() -> None:
    import orjson

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(
        settings.database_url,
        future=True,
        json_serializer=lambda v: orjson.dumps(v).decode("utf-8"),
    )

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

        # Product tables: trigram indexes for fuzzy search + year index
        for brand in ("qbd_mens", "qbd_womens", "yandou", "yiban"):
            table = f"{brand}_products"
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_year ON {table} (year)"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_sku_trgm ON {table} USING GIN (sku gin_trgm_ops)"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_original_sku_trgm ON {table} USING GIN (original_sku gin_trgm_ops)"))

        # Inventory records: filter columns
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_date ON inventory_records (date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_supplier ON inventory_records (supplier)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_warehouse ON inventory_records (warehouse)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_document_type ON inventory_records (document_type)"))

        # Inventory details: FK join column
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_document_id ON inventory_details (document_id)"))

        print("All performance indexes created successfully.")

    engine.dispose()


if __name__ == "__main__":
    main()
