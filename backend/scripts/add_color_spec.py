"""Add color_spec column to inventory_details.

Run: python -m scripts.add_color_spec
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
        conn.execute(text("ALTER TABLE inventory_details ADD COLUMN IF NOT EXISTS color_spec TEXT"))
        print("Added color_spec column to inventory_details.")

    engine.dispose()


if __name__ == "__main__":
    main()
