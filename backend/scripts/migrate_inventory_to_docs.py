"""Migrate inventory_records: drop product_code, rename quantity→total_count, unit_price→amount, create inventory_details.

Run: python -m scripts.migrate_inventory_to_docs
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
        # 1. Drop product_code column
        print("Dropping product_code column...")
        conn.execute(text("ALTER TABLE inventory_records DROP COLUMN IF EXISTS product_code"))

        # 2. Rename quantity → total_count
        print("Renaming quantity → total_count...")
        conn.execute(text("ALTER TABLE inventory_records RENAME COLUMN quantity TO total_count"))

        # 3. Rename unit_price → amount
        print("Renaming unit_price → amount...")
        conn.execute(text("ALTER TABLE inventory_records RENAME COLUMN unit_price TO amount"))

        # 4. Drop unique constraint on summary (if exists)
        print("Dropping uq_inventory_summary constraint...")
        conn.execute(text("ALTER TABLE inventory_records DROP CONSTRAINT IF EXISTS uq_inventory_summary"))

        # 5. Create inventory_details table
        print("Creating inventory_details table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory_details (
                id BIGSERIAL PRIMARY KEY,
                document_id BIGINT NOT NULL REFERENCES inventory_records(id) ON DELETE CASCADE,
                product_code TEXT,
                quantity NUMERIC(10, 2),
                unit_price NUMERIC(10, 2),
                amount NUMERIC(10, 2),
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))

        print("Migration complete.")

    engine.dispose()


if __name__ == "__main__":
    main()
