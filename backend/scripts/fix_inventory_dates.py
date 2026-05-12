"""Fix Excel serial date numbers stored in inventory_records.date and raw_payload.

Run: python -m scripts.fix_inventory_dates
"""
from __future__ import annotations

from datetime import datetime, timedelta

from config import load_settings
from domain.inventory_schema import INVENTORY_TABLE
from domain.inventory_sources import INVENTORY_COLUMN_ALIASES
from sqlalchemy import create_engine, select, update

EXCEL_EPOCH = datetime(1899, 12, 30)

# Keys in raw_payload that map to the "date" field
DATE_RAW_KEYS = {cn for cn, en in INVENTORY_COLUMN_ALIASES.items() if en == "date"}


def normalize_date(value: str | None) -> str | None:
    if not value:
        return value
    try:
        serial = float(value)
        if 1 <= serial <= 100000:
            return (EXCEL_EPOCH + timedelta(days=int(serial))).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    return value


def main() -> None:
    import orjson

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(
        settings.database_url,
        future=True,
        json_serializer=lambda v: orjson.dumps(v).decode("utf-8"),
    )
    table = INVENTORY_TABLE

    with engine.begin() as conn:
        rows = conn.execute(select(table.c.id, table.c.date, table.c.raw_payload)).all()
        date_fixed = 0
        raw_fixed = 0
        for row_id, date_val, raw_payload in rows:
            # Fix date field
            new_date = normalize_date(date_val)
            if new_date != date_val:
                conn.execute(update(table).where(table.c.id == row_id).values(date=new_date))
                date_fixed += 1
                if date_fixed <= 5:
                    print(f"  date id={row_id}: {date_val} -> {new_date}")

            # Fix raw_payload date
            if raw_payload and isinstance(raw_payload, dict):
                changed = False
                for key in list(raw_payload):
                    if key in DATE_RAW_KEYS:
                        old_val = raw_payload[key]
                        if isinstance(old_val, str):
                            new_val = normalize_date(old_val)
                            if new_val != old_val:
                                raw_payload[key] = new_val
                                changed = True
                                if raw_fixed < 5:
                                    print(f"  raw_payload id={row_id}: {old_val} -> {new_val}")
                if changed:
                    conn.execute(update(table).where(table.c.id == row_id).values(raw_payload=raw_payload))
                    raw_fixed += 1

        print(f"Fixed date field: {date_fixed}, raw_payload dates: {raw_fixed}")

    engine.dispose()


if __name__ == "__main__":
    main()
