from __future__ import annotations

from collections.abc import Iterable

import orjson
from sqlalchemy import create_engine, delete, insert

from domain.schema import METADATA, PRODUCT_TABLES
from domain.inventory_schema import INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, JST_STOCK_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE  # noqa: F401 - register on METADATA
from domain import vip_schema  # noqa: F401 - register VIP/JST analytics tables on METADATA


def _json_serializer(value):
    return orjson.dumps(value)


class Database:
    def __init__(self, database_url: str | None):
        self.engine = create_engine(database_url, future=True, json_serializer=_json_serializer) if database_url else None

    def _require_engine(self):
        if self.engine is None:
            raise ValueError("DATABASE_URL is required for database operations")
        return self.engine

    def create_tables(self) -> None:
        engine = self._require_engine()
        METADATA.create_all(engine, checkfirst=True)

    def replace_brand_rows(self, brand_group: str, rows: Iterable[dict[str, object]]) -> int:
        table = PRODUCT_TABLES[brand_group]
        payload = list(rows)

        # Deduplicate by sku: keep the last occurrence (later workbook overwrites earlier)
        seen: dict[str, int] = {}
        for idx, row in enumerate(payload):
            sku = row.get("sku")
            if sku is not None and str(sku).strip():
                seen[str(sku).strip()] = idx

        if len(seen) < len(payload):
            # Some duplicates found - keep only the last occurrence of each sku,
            # and all rows without a sku
            deduped: list[dict[str, object]] = []
            kept: set[int] = set()
            # First pass: rows without sku (keep all)
            for idx, row in enumerate(payload):
                sku = row.get("sku")
                if not sku or not str(sku).strip():
                    deduped.append(row)
                    kept.add(idx)
            # Second pass: rows with sku (keep only last occurrence)
            for idx in sorted(seen.values()):
                if idx not in kept:
                    deduped.append(payload[idx])
            payload = deduped

        with self._require_engine().begin() as connection:
            connection.execute(delete(table))
            if payload:
                connection.execute(insert(table), payload)
        return len(payload)

    def ping(self) -> None:
        with self._require_engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
