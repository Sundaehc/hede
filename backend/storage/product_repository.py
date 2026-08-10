from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal
from typing import Callable

import orjson
from sqlalchemy import and_, bindparam, create_engine, delete, desc, func, insert, literal, or_, select, text, union_all, update

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.excluded_skus import not_excluded_sku_condition
from domain.product_defaults import apply_product_defaults
from domain.schema import PRODUCT_ARCHIVE_TABLES, PRODUCT_TABLES
from domain.vip_schema import JST_PRICE_TABLE


def _json_serializer(value: object) -> bytes:
    return orjson.dumps(value)


# PostgreSQL accepts this safely and it avoids repeatedly scanning the large
# historical price table during full product exports.
PRICE_LOOKUP_CHUNK_SIZE = 20000
IMPORT_MARK_CHUNK_SIZE = 2000
PRODUCT_COLOR_BARCODE_SOURCE_BRANDS = {
    "cbanner_mens": "cbanner_mens",
    "cbanner_womens": "cbanner_womens",
    "yandou": "cbanner_mens",
    "eblan": "cbanner_mens",
    "ni": "ni",
}
COMBINED_FOOTWEAR_PRICE_SOURCE_MARKER = "男女鞋合并物价"


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


def _unique_color_codes(rows: list[Mapping[str, object]]) -> dict[str, str]:
    codes_by_name: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        color_name = _normalize_code(row.get("color_name"))
        color_code = _normalize_code(row.get("color_barcode"))
        if color_name and color_code:
            codes_by_name[color_name].add(color_code)
    return {
        color_name: next(iter(codes))
        for color_name, codes in codes_by_name.items()
        if len(codes) == 1
    }


def _load_jst_product_costs(engine, codes: set[str]) -> dict[str, object]:
    return _load_jst_product_prices(engine, codes, value_column="preset_price")


def _load_jst_product_prices(
    engine,
    codes: set[str],
    *,
    value_column: str,
) -> dict[str, object]:
    if not codes:
        return {}

    price_column = getattr(JST_PRICE_TABLE.c, value_column)
    costs: dict[str, object] = {}
    with engine.connect() as connection:
        for chunk in _chunk_codes(codes):
            statement = (
                select(
                    JST_PRICE_TABLE.c.goods_code,
                    price_column.label("price_value"),
                )
                # PostgreSQL's DISTINCT ON keeps only the latest price per
                # goods code before rows are sent back to the application.
                .distinct(JST_PRICE_TABLE.c.goods_code)
                .where(JST_PRICE_TABLE.c.goods_code.in_(chunk))
                .where(JST_PRICE_TABLE.c.source_workbook.ilike(f"%{COMBINED_FOOTWEAR_PRICE_SOURCE_MARKER}%"))
                .where(price_column.isnot(None))
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
                costs[code] = row["price_value"]
    return costs


def _apply_cost_lookup(items: list[dict[str, object]], costs: dict[str, object]) -> None:
    for item in items:
        sku = _normalize_code(item.get("sku"))
        original_sku = _normalize_code(item.get("original_sku"))
        if sku in costs:
            item["cost"] = costs[sku]
        elif original_sku in costs:
            item["cost"] = costs[original_sku]


def apply_jst_product_costs(engine, items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Apply latest combined-footwear preset price as the archive cost."""
    codes = {
        code
        for item in items
        for code in (_normalize_code(item.get("sku")), _normalize_code(item.get("original_sku")))
        if code
    }
    if not codes:
        return items

    _apply_cost_lookup(items, _load_jst_product_costs(engine, codes))
    return items


def _same_cost(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (ArithmeticError, ValueError):
        return left == right


class ProductRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )
        self._color_code_cache: dict[str, dict[str, str]] = {}

    def create_tables(self) -> None:
        """Apply lightweight, backwards-compatible product archive schema additions."""
        with self.engine.begin() as connection:
            for table in PRODUCT_ARCHIVE_TABLES.values():
                table.create(connection, checkfirst=True)
                connection.execute(text(
                    f"ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS last_imported_at TIMESTAMPTZ"
                ))
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS idx_{table.name}_last_imported_at "
                    f"ON {table.name} (last_imported_at)"
                ))

    def sync_costs_from_latest_combined_footwear_price(
        self,
        *,
        brands: set[str] | None = None,
    ) -> dict[str, object]:
        """Persist latest combined-footwear preset prices into product archives."""
        rows_by_brand: dict[str, list[dict[str, object]]] = {}
        codes: set[str] = set()
        with self.engine.connect() as connection:
            for brand, table in PRODUCT_ARCHIVE_TABLES.items():
                if brands is not None and brand not in brands:
                    continue
                rows = [
                    dict(row)
                    for row in connection.execute(
                        select(table.c.id, table.c.sku, table.c.original_sku, table.c.cost)
                    ).mappings()
                ]
                rows_by_brand[brand] = rows
                for row in rows:
                    for code in (_normalize_code(row.get("sku")), _normalize_code(row.get("original_sku"))):
                        if code:
                            codes.add(code)

        source_costs = _load_jst_product_costs(self.engine, codes)
        summary: dict[str, dict[str, int]] = {}
        with self.engine.begin() as connection:
            for brand, rows in rows_by_brand.items():
                updates: list[dict[str, object]] = []
                matched = 0
                for row in rows:
                    sku = _normalize_code(row.get("sku"))
                    original_sku = _normalize_code(row.get("original_sku"))
                    cost = source_costs.get(sku)
                    if cost is None:
                        cost = source_costs.get(original_sku)
                    if cost is None:
                        continue
                    matched += 1
                    if not _same_cost(row.get("cost"), cost):
                        updates.append({"product_id": row["id"], "new_cost": cost})

                if updates:
                    connection.execute(
                        update(PRODUCT_ARCHIVE_TABLES[brand])
                        .where(PRODUCT_ARCHIVE_TABLES[brand].c.id == bindparam("product_id"))
                        .values(cost=bindparam("new_cost")),
                        updates,
                    )
                summary[brand] = {
                    "matched": matched,
                    "updated": len(updates),
                }

        return {
            "source": f"{COMBINED_FOOTWEAR_PRICE_SOURCE_MARKER}（预设售价）",
            "updated": sum(item["updated"] for item in summary.values()),
            "brands": summary,
        }

    def _color_codes_for_brand(self, brand: str) -> dict[str, str]:
        source_brand = PRODUCT_COLOR_BARCODE_SOURCE_BRANDS.get(brand)
        if source_brand is None:
            return {}
        cached = self._color_code_cache.get(source_brand)
        if cached is not None:
            return cached
        with self.engine.connect() as connection:
            rows = list(connection.execute(
                select(
                    COLOR_BARCODE_TABLE.c.color_name,
                    COLOR_BARCODE_TABLE.c.color_barcode,
                ).where(COLOR_BARCODE_TABLE.c.brand == source_brand)
            ).mappings())
        codes = _unique_color_codes(rows)
        self._color_code_cache[source_brand] = codes
        return codes

    def backfill_missing_color_codes(self) -> dict[str, int]:
        updated_by_brand: dict[str, int] = {}
        with self.engine.begin() as connection:
            color_codes_by_source = {
                source_brand: _unique_color_codes(list(connection.execute(
                    select(
                        COLOR_BARCODE_TABLE.c.color_name,
                        COLOR_BARCODE_TABLE.c.color_barcode,
                    ).where(COLOR_BARCODE_TABLE.c.brand == source_brand)
                ).mappings()))
                for source_brand in set(PRODUCT_COLOR_BARCODE_SOURCE_BRANDS.values())
            }
            self._color_code_cache.update(color_codes_by_source)

            for brand, table in PRODUCT_TABLES.items():
                color_codes = color_codes_by_source[PRODUCT_COLOR_BARCODE_SOURCE_BRANDS[brand]]
                rows = connection.execute(
                    select(table.c.id, table.c.color)
                    .where(table.c.color.is_not(None))
                    .where(table.c.color != "")
                    .where(or_(table.c.color_code.is_(None), table.c.color_code == ""))
                ).mappings()
                updates = [
                    {"product_id": row["id"], "new_color_code": color_codes[color_name]}
                    for row in rows
                    if (color_name := _normalize_code(row.get("color"))) in color_codes
                ]
                if updates:
                    connection.execute(
                        update(table)
                        .where(table.c.id == bindparam("product_id"))
                        .values(color_code=bindparam("new_color_code")),
                        updates,
                    )
                updated_by_brand[brand] = len(updates)
        return updated_by_brand

    def list_products(
        self,
        brand: str,
        query: str | None,
        page: int,
        page_size: int,
        year: str | None = None,
    ) -> dict[str, object]:
        table = PRODUCT_ARCHIVE_TABLES[brand]
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
        brand_keys = list(PRODUCT_ARCHIVE_TABLES.keys())

        subqueries = []
        for brand_key in brand_keys:
            table = PRODUCT_ARCHIVE_TABLES[brand_key]
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
        table = PRODUCT_ARCHIVE_TABLES[brand]
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
        table = PRODUCT_ARCHIVE_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.id.in_(ids))
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
            .order_by(desc(table.c.id))
        )
        with self.engine.connect() as connection:
            items = [dict(row) for row in connection.execute(statement).mappings()]
        return apply_jst_product_costs(self.engine, items)

    def mark_products_imported(self, brand: str, product_ids: list[int], *, connection=None) -> None:
        ids = sorted({int(product_id) for product_id in product_ids})
        if not ids:
            return
        table = PRODUCT_ARCHIVE_TABLES[brand]
        def mark_imported(active_connection) -> None:
            for index in range(0, len(ids), IMPORT_MARK_CHUNK_SIZE):
                active_connection.execute(
                    update(table)
                    .where(table.c.id.in_(ids[index:index + IMPORT_MARK_CHUNK_SIZE]))
                    .values(last_imported_at=func.now())
                )
        if connection is not None:
            mark_imported(connection)
            return
        with self.engine.begin() as active_connection:
            mark_imported(active_connection)

    def find_by_sku(self, brand: str, sku: object, *, connection=None) -> dict[str, object] | None:
        table = PRODUCT_ARCHIVE_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.sku == str(sku))
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
        )
        if connection is not None:
            row = connection.execute(statement).mappings().first()
        else:
            with self.engine.connect() as active_connection:
                row = active_connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def find_by_original_sku(self, brand: str, original_sku: object, *, connection=None) -> dict[str, object] | None:
        table = PRODUCT_ARCHIVE_TABLES[brand]
        statement = (
            select(table)
            .where(table.c.original_sku == str(original_sku))
            .where(not_excluded_sku_condition(table.c.sku, table.c.original_sku))
        )
        if connection is not None:
            row = connection.execute(statement).mappings().first()
        else:
            with self.engine.connect() as active_connection:
                row = active_connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def upsert_by_sku(self, brand: str, record: Mapping[str, object]) -> dict[str, object]:
        table = PRODUCT_ARCHIVE_TABLES[brand]
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

    def create_product(self, brand: str, record: Mapping[str, object], *, connection=None) -> dict[str, object]:
        table = PRODUCT_ARCHIVE_TABLES[brand]
        statement = insert(table).values(**self._prepare_record(record, brand=brand)).returning(table)
        if connection is not None:
            row = connection.execute(statement).mappings().one()
            return dict(row)
        with self.engine.begin() as active_connection:
            row = active_connection.execute(statement).mappings().one()
        item = dict(row)
        apply_jst_product_costs(self.engine, [item])
        return item

    def update_product(
        self,
        brand: str,
        product_id: int,
        record: Mapping[str, object],
        *,
        connection=None,
    ) -> dict[str, object] | None:
        table = PRODUCT_ARCHIVE_TABLES[brand]
        payload = self._prepare_record(record, brand=brand)
        payload.pop("id", None)
        statement = update(table).where(table.c.id == product_id).values(**payload).returning(table)
        if connection is not None:
            row = connection.execute(statement).mappings().first()
            return None if row is None else dict(row)
        with self.engine.begin() as active_connection:
            row = active_connection.execute(statement).mappings().first()
        if row is None:
            return None
        item = dict(row)
        apply_jst_product_costs(self.engine, [item])
        return item

    def delete_product(self, brand: str, product_id: int) -> bool:
        table = PRODUCT_ARCHIVE_TABLES[brand]
        statement = delete(table).where(table.c.id == product_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def delete_products(self, brand: str, ids: list[int]) -> int:
        if not ids:
            return 0
        table = PRODUCT_ARCHIVE_TABLES[brand]
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
        table = PRODUCT_ARCHIVE_TABLES[brand]
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

    def _prepare_record(self, record: Mapping[str, object], *, brand: str | None = None) -> dict[str, object]:
        payload = dict(record)
        if brand is not None:
            payload = dict(apply_product_defaults(brand, payload))
            color_name = _normalize_code(payload.get("color"))
            color_code = _normalize_code(payload.get("color_code"))
            if color_name and not color_code:
                resolved_color_code = self._color_codes_for_brand(brand).get(color_name)
                if resolved_color_code:
                    payload["color_code"] = resolved_color_code
        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            payload["raw_payload"] = {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in raw_payload.items()
            }
        return payload
