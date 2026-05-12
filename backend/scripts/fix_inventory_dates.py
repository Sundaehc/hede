"""Fix Excel serial date numbers stored in inventory_records.date field.

Run: python -m scripts.fix_inventory_dates
"""
from __future__ import annotations

from datetime import datetime, timedelta

from config import load_settings
from domain.inventory_schema import INVENTORY_TABLE
from sqlalchemy import create_engine, select, update

EXCEL_EPOCH = datetime(1899, 12, 30)


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
    settings = load_settings()
    engine = create_engine(settings.database_url, future=True)
    table = INVENTORY_TABLE

    with engine.begin() as conn:
        rows = conn.execute(select(table.c.id, table.c.date)).all()
        fixed = 0
        for row_id, date_val in rows:
            new_date = normalize_date(date_val)
            if new_date != date_val:
                conn.execute(update(table).where(table.c.id == row_id).values(date=new_date))
                fixed += 1
                if fixed <= 10:
                    print(f"  id={row_id}: {date_val} -> {new_date}")
        print(f"Fixed {fixed} records")

    engine.dispose()


if __name__ == "__main__":
    main()
