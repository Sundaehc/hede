from __future__ import annotations

from collections.abc import Iterable

import orjson
from sqlalchemy import create_engine, delete, func, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.product_defaults import apply_product_defaults
from domain.schema import METADATA, PRODUCT_TABLES
from domain import fine_table_snapshot_schema  # noqa: F401 - register fine table snapshot tables on METADATA
from domain.inventory_schema import INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, JST_STOCK_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE  # noqa: F401 - register on METADATA
from domain import task_status_schema  # noqa: F401 - register scheduled task status tables on METADATA
from domain import vip_schema  # noqa: F401 - register VIP/JST analytics tables on METADATA
from domain import gj_schema  # noqa: F401 - register GJ export tables on METADATA


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
        payload = [dict(apply_product_defaults(brand_group, dict(row))) for row in rows]

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

    def upsert_brand_rows(self, brand_group: str, rows: Iterable[dict[str, object]]) -> int:
        table = PRODUCT_TABLES[brand_group]
        payload = self._dedupe_by_sku(
            [dict(apply_product_defaults(brand_group, dict(row))) for row in rows]
        )
        if not payload:
            return 0

        update_columns = [
            column.name
            for column in table.columns
            if column.name not in ("id", "sku", "created_at")
        ]

        with self._require_engine().begin() as connection:
            for index in range(0, len(payload), 1000):
                stmt = pg_insert(table).values(payload[index:index + 1000])
                excluded = stmt.excluded
                set_values = {column: getattr(excluded, column) for column in update_columns}
                set_values["image_path"] = func.coalesce(getattr(excluded, "image_path"), table.c.image_path)
                set_values["updated_at"] = func.date_trunc("minute", func.now())
                stmt = stmt.on_conflict_do_update(
                    index_elements=["sku"],
                    set_=set_values,
                )
                connection.execute(stmt)
        return len(payload)

    @staticmethod
    def _dedupe_by_sku(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        seen: dict[str, int] = {}
        for idx, row in enumerate(rows):
            sku = row.get("sku")
            if sku is not None and str(sku).strip():
                seen[str(sku).strip()] = idx

        if len(seen) >= len(rows):
            return rows

        deduped: list[dict[str, object]] = []
        kept: set[int] = set()
        for idx, row in enumerate(rows):
            sku = row.get("sku")
            if not sku or not str(sku).strip():
                deduped.append(row)
                kept.add(idx)
        for idx in sorted(seen.values()):
            if idx not in kept:
                deduped.append(rows[idx])
        return deduped

    def ping(self) -> None:
        with self._require_engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
