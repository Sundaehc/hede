from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Callable

import orjson
from sqlalchemy import and_, create_engine, delete, desc, func, insert, literal, or_, select, union_all, update

from domain.excluded_skus import not_excluded_sku_condition
from domain.product_defaults import apply_product_defaults
from domain.schema import PRODUCT_TABLES
from domain.vip_schema import JST_PRICE_TABLE


def _json_serializer(value: object) -> bytes:
    return orjson.dumps(value)


PRICE_LOOKUP_CHUNK_SIZE = 2000


def _normalize_code(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _chunk_codes(codes: set[str]) -> list[list[str]]:
    ordered = sorted(codes)
    return [
        ordered[index:index + PRICE_LOOKUP_CHUNK_SIZE]
        for index in range(0, len(ordered), PRICE_LOOKUP_CHUNK_SIZE)
    ]


def _load_jst_product_costs(engine, codes: set[str]) -> dict[str, object | None]:
    if not codes:
        return {}

    costs: dict[str, object | None] = {}
    with engine.connect() as connection:
        for chunk in _chunk_codes(codes):
            statement = (
                select(
                    JST_PRICE_TABLE.c.goods_code,
                    JST_PRICE_TABLE.c.cost_unit_price,
                )
                .where(JST_PRICE_TABLE.c.goods_code.in_(chunk))
                .order_by(
                    JST_PRICE_TABLE.c.goods_code,
                    JST_PRICE_TABLE.c.source_date_value.desc().nulls_last(),
                    desc(JST_PRICE_TABLE.c.updated_at),
                    desc(JST_PRICE_TABLE.c.id),
                )
            )
            for row in connection.execute(statement).mappings():
                code = _normalize_code(row.get("goods_code"))
                if not code or code in costs:
                    continue
                cost = row.get("cost_unit_price")
                if isinstance(cost, str) and not cost.strip():
                    cost = None
                costs[code] = cost
    return costs


def apply_jst_product_costs(engine, items: list[dict[str, object]]) -> list[dict[str, object]]:
    codes = {
        code
        for item in items
        for code in (_normalize_code(item.get("sku")), _normalize_code(item.get("original_sku")))
        if code
    }
    costs = _load_jst_product_costs(engine, codes)
    if not costs:
        return items

    for item in items:
        sku = _normalize_code(item.get("sku"))
        original_sku = _normalize_code(item.get("original_sku"))
        if sku in costs:
            item["cost"] = costs[sku]
        elif original_sku in costs:
            item["cost"] = costs[original_sku]
    return items


class ProductRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )

    def list_products(
        self,
        brand: str,
        query: str | None,
        page: int,
        page_size: int,
        year: str | None = None,
    ) -> dict[str, object]:
        table = PRODUCT_TABLES[brand]
        count_statement = select(func.count()).select_from(table)
        items_statement = select(table)

        conditions = [not_excluded_sku_condition(table.c.sku, table.c.original_sku)]
        if query:
            terms = [t.strip() for t in query.replace("\n", ",").split(",") if t.strip()]
            query_conditions = []
            for term in terms:
                query_conditions.append(table.c.original_sku.ilike(f"%{term}%"))
                query_conditions.append(table.c.sku.ilike(f"%{term}%"))
            conditions.append(or_(*query_conditions))
        if year:
            # year values like "21年春季款" or "2025" — match by prefix
            prefix2 = year[-2:]
            conditions.append(
                or_(table.c.year.startswith(year), table.c.year.startswith(prefix2))
            )

        if conditions:
            criterion = conditions[0] if len(conditions) == 1 else and_(*conditions)
            count_statement = count_statement.where(criterion)
            items_statement = items_statement.where(criterion)

        items_statement = items_statement.order_by(desc(table.c.id)).offset((page - 1) * page_size).limit(page_size)

        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]

        apply_jst_product_costs(self.engine, items)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_all_products(
        self,
        query: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        brand_keys = list(PRODUCT_TABLES.keys())

        subqueries = []
        for brand_key in brand_keys:
            table = PRODUCT_TABLES[brand_key]
            sq = select(
                table.c.id,
                literal(brand_key).label("brand"),
                *([c for c in table.columns if c.key not in ("id",)]),
            )
            sq = sq.where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
            if query:
                terms = [t.strip() for t in query.replace("\n", ",").split(",") if t.strip()]
                conditions = []
                for term in terms:
                    conditions.append(table.c.original_sku.ilike(f"%{term}%"))
                    conditions.append(table.c.sku.ilike(f"%{term}%"))
                sq = sq.where(or_(*conditions))
            subqueries.append(sq)

        combined = union_all(*subqueries).subquery()

        count_statement = select(func.count()).select_from(combined)
        items_statement = select(combined).order_by(desc(combined.c.id)).offset((page - 1) * page_size).limit(page_size)

        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]

        apply_jst_product_costs(self.engine, items)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_product(self, brand: str, product_id: int) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.id == product_id)
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        item = dict(row)
        apply_jst_product_costs(self.engine, [item])
        return item

    def get_products_by_ids(self, brand: str, ids: list[int]) -> list[dict[str, object]]:
        if not ids:
            return []
        table = PRODUCT_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.id.in_(ids))
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
            .order_by(desc(table.c.id))
        )
        with self.engine.connect() as connection:
            items = [dict(row) for row in connection.execute(statement).mappings()]
        return apply_jst_product_costs(self.engine, items)

    def find_by_sku(self, brand: str, sku: object) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.sku == str(sku))
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def find_by_original_sku(self, brand: str, original_sku: object) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.original_sku == str(original_sku))
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def upsert_by_sku(self, brand: str, record: Mapping[str, object]) -> dict[str, object]:
        table = PRODUCT_TABLES[brand]
        payload = self._prepare_record(record, brand=brand)
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
        statement = insert(table).values(**self._prepare_record(record, brand=brand)).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        item = dict(row)
        apply_jst_product_costs(self.engine, [item])
        return item

    def update_product(
        self,
        brand: str,
        product_id: int,
        record: Mapping[str, object],
    ) -> dict[str, object] | None:
        table = PRODUCT_TABLES[brand]
        payload = self._prepare_record(record, brand=brand)
        payload.pop("id", None)
        statement = update(table).where(table.c.id == product_id).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        item = dict(row)
        apply_jst_product_costs(self.engine, [item])
        return item

    def delete_product(self, brand: str, product_id: int) -> bool:
        table = PRODUCT_TABLES[brand]
        statement = delete(table).where(table.c.id == product_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def delete_products(self, brand: str, ids: list[int]) -> int:
        if not ids:
            return 0
        table = PRODUCT_TABLES[brand]
        statement = delete(table).where(table.c.id.in_(ids))
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount

    def refresh_image_paths(
        self,
        brand: str,
        find_image: Callable[[object], str | None],
        *,
        overwrite: bool = False,
    ) -> dict[str, int]:
        table = PRODUCT_TABLES[brand]
        statement = select(table.c.id, table.c.original_sku, table.c.sku, table.c.image_path)
        if not overwrite:
            statement = statement.where(or_(table.c.image_path.is_(None), table.c.image_path == ""))

        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(statement).mappings()]

        updated = 0
        matched = 0
        missing = 0
        with self.engine.begin() as connection:
            for row in rows:
                image_path = None
                original_sku = str(row.get("original_sku") or "").strip()
                sku = str(row.get("sku") or "").strip()
                if original_sku:
                    image_path = find_image(original_sku)
                if not image_path and sku:
                    image_path = find_image(sku)

                if not image_path:
                    missing += 1
                    continue

                matched += 1
                if image_path == row.get("image_path"):
                    continue

                connection.execute(
                    update(table)
                    .where(table.c.id == row["id"])
                    .values(image_path=image_path)
                )
                updated += 1

        return {
            "scanned": len(rows),
            "matched": matched,
            "updated": updated,
            "missing": missing,
        }

    @staticmethod
    def _prepare_record(record: Mapping[str, object], *, brand: str | None = None) -> dict[str, object]:
        payload = dict(record)
        if brand is not None:
            payload = dict(apply_product_defaults(brand, payload))
        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            payload["raw_payload"] = {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in raw_payload.items()
            }
        return payload
