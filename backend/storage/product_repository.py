from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy import create_engine, delete, desc, func, insert, select, update

from domain.schema import PRODUCT_TABLES


class ProductRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)

    def list_products(
        self,
        brand: str,
        query: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        table = PRODUCT_TABLES[brand]
        count_statement = select(func.count()).select_from(table)
        items_statement = select(table)
        if query:
            criterion = table.c.original_sku.ilike(f"%{query}%")
            count_statement = count_statement.where(criterion)
            items_statement = items_statement.where(criterion)

        items_statement = items_statement.order_by(desc(table.c.id)).offset((page - 1) * page_size).limit(page_size)

        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_product(self, brand: str, product_id: int) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        statement = select(table).where(table.c.id == product_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def find_by_sku(self, brand: str, sku: object) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        statement = select(table).where(table.c.sku == str(sku))
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def upsert_by_sku(self, brand: str, record: Mapping[str, object]) -> dict[str, object]:
        table = PRODUCT_TABLES[brand]
        payload = self._prepare_record(record)
        sku = str(payload.get("sku", ""))

        with self.engine.begin() as connection:
            existing = connection.execute(
                select(table).where(table.c.sku == sku)
            ).mappings().first()

            if existing is None:
                row = connection.execute(insert(table).values(**payload).returning(table)).mappings().one()
            else:
                payload.pop("id", None)
                row = connection.execute(
                    update(table).where(table.c.id == existing["id"]).values(**payload).returning(table)
                ).mappings().one()

        return dict(row)

    def create_product(self, brand: str, record: Mapping[str, object]) -> dict[str, object]:
        table = PRODUCT_TABLES[brand]
        statement = insert(table).values(**self._prepare_record(record)).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_product(
        self,
        brand: str,
        product_id: int,
        record: Mapping[str, object],
    ) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        payload = self._prepare_record(record)
        payload.pop("id", None)
        statement = update(table).where(table.c.id == product_id).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_product(self, brand: str, product_id: int) -> bool:
        table = PRODUCT_TABLES[brand]
        statement = delete(table).where(table.c.id == product_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    @staticmethod
    def _prepare_record(record: Mapping[str, object]) -> dict[str, object]:
        payload = dict(record)
        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            payload["raw_payload"] = {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in raw_payload.items()
            }
        return payload

