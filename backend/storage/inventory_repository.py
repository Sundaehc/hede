from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
import secrets
import string

from pathlib import Path

import orjson
from openpyxl import load_workbook
from sqlalchemy import and_, case, create_engine, delete, desc, func, insert, inspect, or_, select, text, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_schema import GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, JST_STOCK_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE
from domain.gj_brand import CBANNER_MENS_BRAND, GJ_FINE_TABLE_BRANDS, infer_supplier_brand_from_name
from storage.date_normalization import parse_date, parse_month_day


def _json_serializer(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


class InventoryRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )
        self.create_tables()

    # ── Inventory Records ──────────────────────────────────────────

    def list_records(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
        supplier: str | None = None,
        warehouse: str | None = None,
        document_type: str | None = None,
        summary: str | None = None,
        original_sku: str | None = None,
        product_code: str | None = None,
        handler: str | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        table = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        stock = JST_STOCK_TABLE
        count_statement = select(func.count()).select_from(table)
        items_statement = select(table)

        conditions = []
        if date_start:
            parsed = parse_date(date_start)
            conditions.append(table.c.date_value >= parsed if parsed else table.c.date >= date_start)
        if date_end:
            parsed = parse_date(date_end)
            conditions.append(table.c.date_value <= parsed if parsed else table.c.date <= date_end)
        if supplier:
            conditions.append(table.c.supplier.ilike(f"%{supplier.strip()}%"))
        if warehouse:
            conditions.append(table.c.warehouse == warehouse)
        if document_type:
            conditions.append(table.c.document_type == document_type)
        if summary:
            conditions.append(table.c.summary.ilike(f"%{summary.strip()}%"))
        if handler:
            conditions.append(table.c.handler.ilike(f"%{handler.strip()}%"))
        if original_sku:
            original_like = f"%{original_sku.strip()}%"
            conditions.append(
                select(detail.c.id)
                .where(
                    detail.c.document_id == table.c.id,
                    detail.c.product_code.ilike(original_like),
                )
                .exists()
            )
        if product_code:
            product_like = f"%{product_code.strip()}%"
            stock_code_matches = stock.c.product_code.ilike(product_like)
            stock_candidates = union_all(
                select(stock.c.product_code.label("candidate"))
                .where(stock_code_matches),
                select(func.left(stock.c.product_code, func.length(stock.c.product_code) - 5).label("candidate"))
                .where(stock_code_matches)
                .where(func.length(stock.c.product_code) > 5),
                select(func.left(stock.c.product_code, func.length(stock.c.product_code) - 3).label("candidate"))
                .where(stock_code_matches)
                .where(func.length(stock.c.product_code) > 3),
                select(func.left(stock.c.product_code, func.length(stock.c.product_code) - 2).label("candidate"))
                .where(stock_code_matches)
                .where(func.length(stock.c.product_code) > 2),
            ).subquery()
            conditions.append(
                select(detail.c.id)
                .where(
                    detail.c.document_id == table.c.id,
                    or_(
                        detail.c.product_code.ilike(product_like),
                        detail.c.product_code.in_(
                            select(stock_candidates.c.candidate)
                            .where(stock_candidates.c.candidate.isnot(None))
                            .where(stock_candidates.c.candidate != "")
                            .distinct()
                        ),
                    ),
                )
                .exists()
            )

        if conditions:
            criterion = conditions[0] if len(conditions) == 1 else and_(*conditions)
            items_statement = items_statement.where(criterion)
            count_statement = count_statement.where(criterion)

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

    def get_record(self, record_id: int) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        statement = select(table).where(table.c.id == record_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def create_record(self, record: Mapping[str, object]) -> dict[str, object]:
        table = INVENTORY_TABLE
        with self.engine.begin() as connection:
            payload = self._prepare_record(record)
            if not payload.get("document_number"):
                payload["document_number"] = self._generate_document_number(connection, payload.get("date_value"))
            statement = insert(table).values(**payload).returning(table)
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_record(self, record_id: int, record: Mapping[str, object]) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        payload = self._prepare_record(record)
        payload.pop("id", None)
        statement = update(table).where(table.c.id == record_id).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_record(self, record_id: int) -> bool:
        table = INVENTORY_TABLE
        statement = delete(table).where(table.c.id == record_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def delete_records(self, ids: list[int]) -> int:
        if not ids:
            return 0
        table = INVENTORY_TABLE
        statement = delete(table).where(table.c.id.in_(ids))
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount

    # ── Suppliers ──────────────────────────────────────────────────

    def list_suppliers(self, *, brand: str | None = None) -> list[dict[str, object]]:
        statement = select(SUPPLIER_TABLE).order_by(SUPPLIER_TABLE.c.brand, SUPPLIER_TABLE.c.id)
        if brand:
            statement = statement.where(SUPPLIER_TABLE.c.brand == brand)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def list_suppliers_page(self, *, page: int, page_size: int, query: str | None = None, brand: str | None = None) -> dict[str, object]:
        count_statement = select(func.count()).select_from(SUPPLIER_TABLE)
        items_statement = (
            select(SUPPLIER_TABLE)
            .order_by(SUPPLIER_TABLE.c.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        conditions = []
        if brand:
            conditions.append(SUPPLIER_TABLE.c.brand == brand)
        normalized_query = (query or "").strip()
        if normalized_query:
            like = f"%{normalized_query}%"
            conditions.append(or_(
                SUPPLIER_TABLE.c.name.ilike(like),
                SUPPLIER_TABLE.c.factory_code.ilike(like),
            ))
        if conditions:
            criterion = conditions[0] if len(conditions) == 1 else and_(*conditions)
            count_statement = count_statement.where(criterion)
            items_statement = items_statement.where(criterion)
        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def create_supplier(self, data: Mapping[str, object]) -> dict[str, object]:
        statement = insert(SUPPLIER_TABLE).values(**self._prepare_supplier(data)).returning(SUPPLIER_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_supplier(self, supplier_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = self._prepare_supplier(data)
        payload.pop("id", None)
        statement = update(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == supplier_id).values(**payload).returning(SUPPLIER_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_supplier(self, supplier_id: int) -> bool:
        statement = delete(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == supplier_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def get_supplier_by_name(self, name: str, brand: str | None = None) -> dict[str, object] | None:
        statement = select(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.name == name)
        if brand:
            statement = statement.where(SUPPLIER_TABLE.c.brand == brand)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    # ── General Customer Brands & Shops ────────────────────────────

    def list_general_customer_brands(self) -> list[dict[str, object]]:
        shop_count = (
            select(
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name.label("brand_name"),
                func.count(GENERAL_CUSTOMER_SHOP_TABLE.c.id).label("shop_count"),
            )
            .group_by(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name)
            .subquery()
        )
        statement = (
            select(
                GENERAL_CUSTOMER_BRAND_TABLE.c.id,
                GENERAL_CUSTOMER_BRAND_TABLE.c.name,
                GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
                GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
                func.coalesce(shop_count.c.shop_count, 0).label("shop_count"),
            )
            .outerjoin(shop_count, shop_count.c.brand_name == GENERAL_CUSTOMER_BRAND_TABLE.c.name)
            .order_by(GENERAL_CUSTOMER_BRAND_TABLE.c.name)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_general_customer_brand(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {"name": str(data.get("name") or "").strip()}
        statement = (
            insert(GENERAL_CUSTOMER_BRAND_TABLE)
            .values(**payload)
            .returning(
                GENERAL_CUSTOMER_BRAND_TABLE.c.id,
                GENERAL_CUSTOMER_BRAND_TABLE.c.name,
                GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
                GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
            )
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        item = dict(row)
        item["shop_count"] = 0
        return item

    def update_general_customer_brand(self, brand_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = {"name": str(data.get("name") or "").strip()}
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(GENERAL_CUSTOMER_BRAND_TABLE.c.name).where(GENERAL_CUSTOMER_BRAND_TABLE.c.id == brand_id)
            ).mappings().first()
            if existing is None:
                return None
            old_name = existing["name"]
            row = connection.execute(
                update(GENERAL_CUSTOMER_BRAND_TABLE)
                .where(GENERAL_CUSTOMER_BRAND_TABLE.c.id == brand_id)
                .values(**payload)
                .returning(
                    GENERAL_CUSTOMER_BRAND_TABLE.c.id,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.name,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
                )
            ).mappings().first()
            if row is None:
                return None
            new_name = row["name"]
            if old_name != new_name:
                connection.execute(
                    update(GENERAL_CUSTOMER_SHOP_TABLE)
                    .where(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == old_name)
                    .values(customer_name=new_name)
                )
            shop_count = connection.execute(
                select(func.count()).select_from(GENERAL_CUSTOMER_SHOP_TABLE).where(
                    GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == new_name
                )
            ).scalar_one()
        item = dict(row)
        item["shop_count"] = shop_count
        return item

    def delete_general_customer_brand(self, brand_id: int) -> str | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(GENERAL_CUSTOMER_BRAND_TABLE.c.name).where(GENERAL_CUSTOMER_BRAND_TABLE.c.id == brand_id)
            ).first()
            if row is None:
                return "not_found"
            brand_name = row[0]
            connection.execute(delete(GENERAL_CUSTOMER_SHOP_TABLE).where(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == brand_name))
            result = connection.execute(delete(GENERAL_CUSTOMER_BRAND_TABLE).where(GENERAL_CUSTOMER_BRAND_TABLE.c.id == brand_id))
        return None if result.rowcount > 0 else "not_found"

    def get_general_customer_brand_by_name(self, name: str) -> dict[str, object] | None:
        statement = select(
            GENERAL_CUSTOMER_BRAND_TABLE.c.id,
            GENERAL_CUSTOMER_BRAND_TABLE.c.name,
            GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
            GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
        ).where(GENERAL_CUSTOMER_BRAND_TABLE.c.name == name)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def list_general_customer_shops(self) -> list[dict[str, object]]:
        statement = (
            select(
                GENERAL_CUSTOMER_SHOP_TABLE.c.id,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
                GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
            )
            .order_by(
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.id,
            )
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_general_customer_shop(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "customer_name": str(data.get("customer_name") or "").strip(),
            "shop_name": str(data.get("shop_name") or "").strip(),
        }
        statement = (
            insert(GENERAL_CUSTOMER_SHOP_TABLE)
            .values(**payload)
            .returning(
                GENERAL_CUSTOMER_SHOP_TABLE.c.id,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
                GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
            )
        )
        with self.engine.begin() as connection:
            self._ensure_general_customer_brand(connection, payload["customer_name"])
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_general_customer_shop(self, shop_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = {
            "customer_name": str(data.get("customer_name") or "").strip(),
            "shop_name": str(data.get("shop_name") or "").strip(),
        }
        statement = (
            update(GENERAL_CUSTOMER_SHOP_TABLE)
            .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id)
            .values(**payload)
            .returning(
                GENERAL_CUSTOMER_SHOP_TABLE.c.id,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
                GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
            )
        )
        with self.engine.begin() as connection:
            self._ensure_general_customer_brand(connection, payload["customer_name"])
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_general_customer_shop(self, shop_id: int) -> bool:
        statement = delete(GENERAL_CUSTOMER_SHOP_TABLE).where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def get_general_customer_shop_by_name(self, customer_name: str, shop_name: str) -> dict[str, object] | None:
        statement = select(
            GENERAL_CUSTOMER_SHOP_TABLE.c.id,
            GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
            GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
        ).where(
            GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == customer_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name == shop_name,
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    # ── Warehouses ─────────────────────────────────────────────────

    def list_warehouses(self) -> list[dict[str, object]]:
        statement = select(WAREHOUSE_TABLE).order_by(WAREHOUSE_TABLE.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_warehouse(self, data: Mapping[str, object]) -> dict[str, object]:
        statement = insert(WAREHOUSE_TABLE).values(**dict(data)).returning(WAREHOUSE_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_warehouse(self, warehouse_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = dict(data)
        payload.pop("id", None)
        statement = update(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.id == warehouse_id).values(**payload).returning(WAREHOUSE_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_warehouse(self, warehouse_id: int) -> bool:
        statement = delete(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.id == warehouse_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def get_warehouse_by_name(self, name: str) -> dict[str, object] | None:
        statement = select(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.name == name)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    # ── Inventory Details ───────────────────────────────────────────

    def list_details(self, document_id: int) -> list[dict[str, object]]:
        table = INVENTORY_DETAIL_TABLE
        statement = select(table).where(table.c.document_id == document_id).order_by(table.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def list_details_for_documents(self, document_ids: list[int]) -> list[dict[str, object]]:
        if not document_ids:
            return []
        table = INVENTORY_DETAIL_TABLE
        statement = (
            select(table)
            .where(table.c.document_id.in_(document_ids))
            .order_by(table.c.document_id, table.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_detail(self, data: Mapping[str, object]) -> dict[str, object]:
        table = INVENTORY_DETAIL_TABLE
        payload = self._coerce_empty(data)
        statement = insert(table).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        self.recalculate_totals(payload.get("document_id"))
        return dict(row)

    def create_details(self, rows: list[Mapping[str, object]], document_id: object) -> int:
        if not rows:
            return 0
        table = INVENTORY_DETAIL_TABLE
        payload = [self._coerce_empty(row) for row in rows]
        with self.engine.begin() as connection:
            result = connection.execute(insert(table), payload)
        self.recalculate_totals(document_id)
        return result.rowcount if result.rowcount and result.rowcount > 0 else len(payload)

    def update_detail(self, detail_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        table = INVENTORY_DETAIL_TABLE
        payload = self._coerce_empty(data)
        document_id = payload.pop("document_id", None)
        statement = update(table).where(table.c.id == detail_id).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        if document_id is not None:
            self.recalculate_totals(document_id)
        else:
            detail = dict(row)
            self.recalculate_totals(detail.get("document_id"))
        return dict(row)

    def delete_detail(self, detail_id: int) -> bool:
        table = INVENTORY_DETAIL_TABLE
        # Get document_id before deleting for recalculation
        with self.engine.connect() as connection:
            detail = connection.execute(select(table.c.document_id).where(table.c.id == detail_id)).first()
        document_id = detail[0] if detail else None
        statement = delete(table).where(table.c.id == detail_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        if result.rowcount > 0 and document_id is not None:
            self.recalculate_totals(document_id)
        return result.rowcount > 0

    def recalculate_totals(self, document_id: object) -> None:
        table = INVENTORY_DETAIL_TABLE
        stmt = select(
            func.coalesce(func.sum(table.c.quantity), 0),
            func.coalesce(func.sum(table.c.amount), 0),
        ).where(table.c.document_id == document_id)
        with self.engine.connect() as connection:
            total_count, amount = connection.execute(stmt).one()
        update_stmt = (
            update(INVENTORY_TABLE)
            .where(INVENTORY_TABLE.c.id == document_id)
            .values(total_count=total_count, amount=amount)
        )
        with self.engine.begin() as connection:
            connection.execute(update_stmt)

    def batch_update_purchase_costs(
        self,
        *,
        date_start: str | None,
        date_end: str | None,
        price_updates: Mapping[str, object],
    ) -> dict[str, object]:
        normalized_updates = {
            str(product_code or "").strip(): Decimal(str(unit_price).strip())
            for product_code, unit_price in price_updates.items()
            if str(product_code or "").strip() and str(unit_price or "").strip()
        }
        if not normalized_updates:
            return {"updated_details": 0, "updated_documents": 0, "items": []}

        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        conditions = [
            record.c.document_type.in_(("进货单", "进货退货单")),
            detail.c.product_code.in_(normalized_updates.keys()),
        ]
        if date_start:
            parsed = parse_date(date_start)
            conditions.append(record.c.date_value >= parsed if parsed else record.c.date >= date_start)
        if date_end:
            parsed = parse_date(date_end)
            conditions.append(record.c.date_value <= parsed if parsed else record.c.date <= date_end)

        joined = detail.join(record, detail.c.document_id == record.c.id)
        select_stmt = (
            select(
                detail.c.id,
                detail.c.document_id,
                detail.c.product_code,
                detail.c.quantity,
                detail.c.unit_price,
                detail.c.amount,
                record.c.document_number,
                record.c.date,
                record.c.document_type,
            )
            .select_from(joined)
            .where(and_(*conditions))
            .order_by(record.c.date_value, record.c.id, detail.c.id)
        )

        changed_document_ids: set[int] = set()
        updated_items: list[dict[str, object]] = []
        with self.engine.begin() as connection:
            rows = [dict(row) for row in connection.execute(select_stmt).mappings()]
            for row in rows:
                product_code = str(row.get("product_code") or "").strip()
                new_price = normalized_updates.get(product_code)
                if new_price is None:
                    continue
                quantity = Decimal(str(row.get("quantity") or "0"))
                old_price = row.get("unit_price")
                new_amount = quantity * new_price
                connection.execute(
                    update(detail)
                    .where(detail.c.id == row["id"])
                    .values(unit_price=new_price, amount=new_amount)
                )
                changed_document_ids.add(int(row["document_id"]))
                updated_items.append({
                    "detail_id": row["id"],
                    "document_id": row["document_id"],
                    "document_number": row.get("document_number"),
                    "date": row.get("date"),
                    "document_type": row.get("document_type"),
                    "product_code": product_code,
                    "quantity": str(quantity.normalize()) if quantity.as_tuple().exponent < 0 else str(int(quantity)),
                    "old_unit_price": None if old_price is None else str(old_price),
                    "new_unit_price": str(new_price),
                    "new_amount": str(new_amount),
                })

            for document_id in changed_document_ids:
                totals = connection.execute(
                    select(
                        func.coalesce(func.sum(detail.c.quantity), 0),
                        func.coalesce(func.sum(detail.c.amount), 0),
                    ).where(detail.c.document_id == document_id)
                ).one()
                connection.execute(
                    update(record)
                    .where(record.c.id == document_id)
                    .values(total_count=totals[0], amount=totals[1])
                )

        return {
            "updated_details": len(updated_items),
            "updated_documents": len(changed_document_ids),
            "items": updated_items,
        }

    # ── Ending Inventory ─────────────────────────────────────────────

    def get_ending_inventory(
        self,
        *,
        jst_stock_root: Path | None,
        stock_date: str,
        date_start: str | None = None,
        date_end: str | None = None,
        product_code: str | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        detail = INVENTORY_DETAIL_TABLE
        record = INVENTORY_TABLE

        # Build the aggregated inventory changes query
        inbound_types = ("进货单", "报溢单", "批发销售退货单")
        outbound_types = ("进货退货单", "报损单", "批发销售单")
        inbound = func.sum(case(
            (record.c.document_type.in_(inbound_types), detail.c.quantity),
            else_=0,
        ))
        return_qty = func.sum(case(
            (record.c.document_type.in_(outbound_types), detail.c.quantity),
            else_=0,
        ))

        joined = detail.join(record, detail.c.document_id == record.c.id)
        conditions = []
        if date_start:
            parsed = parse_date(date_start)
            conditions.append(record.c.date_value >= parsed if parsed else record.c.date >= date_start)
        if date_end:
            parsed = parse_date(date_end)
            conditions.append(record.c.date_value <= parsed if parsed else record.c.date <= date_end)
        if product_code:
            conditions.append(detail.c.product_code.like(f"{product_code}%"))
        criterion = and_(*conditions) if conditions else None

        base = (
            select(
                detail.c.product_code,
                detail.c.product_name,
                detail.c.color_spec,
                func.min(record.c.date).label("first_doc_date"),
                inbound.label("inbound_qty"),
                return_qty.label("return_qty"),
            )
            .select_from(joined)
            .group_by(detail.c.product_code, detail.c.product_name, detail.c.color_spec)
        )
        if criterion is not None:
            base = base.where(criterion)

        # Subquery for counting total groups
        sub = base.subquery()
        count_stmt = select(func.count()).select_from(sub)
        with self.engine.connect() as connection:
            total = connection.execute(count_stmt).scalar_one()

        # Paginated query
        data_stmt = (
            select(sub)
            .order_by(sub.c.product_code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(data_stmt).mappings()]

        # Determine beginning stock for each product
        # If date_start is given, all products share the same beginning date.
        # Otherwise, each product uses its own earliest document date.

        def _fmt(v: int | Decimal) -> str:
            if isinstance(v, int):
                return str(v)
            d = v.normalize()
            return str(d) if d.as_tuple().exponent < 0 else str(int(d))

        def _to_mmdd(date_str: str) -> str:
            """Convert YYYY-MM-DD to MM.DD."""
            try:
                parts = date_str.split("-")
                return f"{parts[1]}.{parts[2]}"
            except (IndexError, ValueError):
                return stock_date

        beginning_by_date: dict[str, dict[str, int]] = {}

        def _stock_for_date(mmdd: str) -> dict[str, int]:
            if mmdd not in beginning_by_date:
                beginning_by_date[mmdd] = self._read_jst_stock(jst_stock_root, mmdd) if jst_stock_root else {}
            return beginning_by_date[mmdd]

        if date_start:
            # Global beginning stock date
            begin_date = _to_mmdd(date_start)
            global_stock = _stock_for_date(begin_date)
        else:
            global_stock = None

        items = []
        for row in rows:
            code = row.get("product_code") or ""
            if global_stock is not None:
                beginning = global_stock.get(str(code), 0)
            else:
                first_date = row.get("first_doc_date")
                if first_date:
                    per_stock = _stock_for_date(_to_mmdd(str(first_date)))
                    beginning = per_stock.get(str(code), 0)
                else:
                    beginning = 0

            inbound_val = row.get("inbound_qty") or Decimal("0")
            return_val = row.get("return_qty") or Decimal("0")
            ending = beginning + inbound_val - return_val

            items.append({
                "product_code": row.get("product_code"),
                "product_name": row.get("product_name"),
                "color_spec": row.get("color_spec"),
                "beginning_qty": _fmt(beginning),
                "inbound_qty": _fmt(inbound_val),
                "return_qty": _fmt(return_val),
                "ending_qty": _fmt(ending),
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _read_jst_stock(self, jst_stock_root: Path | None, stock_date: str) -> dict:
        """Read beginning stock from DB, fallback to Excel if no data."""
        if jst_stock_root is None:
            return {}

        # Try DB first
        table = JST_STOCK_TABLE
        stmt = select(table.c.product_code, table.c.available_qty).where(table.c.stock_date == stock_date)
        with self.engine.connect() as connection:
            rows = connection.execute(stmt).all()

        if rows:
            return {str(row.product_code): int(row.available_qty) for row in rows}

        # Fallback to Excel
        return self._read_jst_stock_from_excel(jst_stock_root, stock_date)

    def import_jst_stock(self, jst_stock_root: Path | None, stock_date: str) -> dict[str, object]:
        """Import daily stock from 聚水潭 Excel into jst_daily_stock table."""
        if jst_stock_root is None:
            return {"imported": 0, "message": "JST_STOCK_ROOT 未配置"}

        data = self._read_jst_stock_from_excel(jst_stock_root, stock_date)
        if not data:
            return {"imported": 0, "message": f"未找到 {stock_date} 的库存数据"}

        table = JST_STOCK_TABLE
        stock_date_value = parse_month_day(stock_date)
        rows = [
            {
                "stock_date": stock_date,
                "stock_date_value": stock_date_value,
                "product_code": product_code,
                "available_qty": qty,
            }
            for product_code, qty in data.items()
        ]
        with self.engine.begin() as connection:
            for i in range(0, len(rows), 1000):
                stmt = pg_insert(table).values(rows[i:i + 1000]).on_conflict_do_update(
                    index_elements=["stock_date", "product_code"],
                    set_={
                        "stock_date_value": pg_insert(table).excluded.stock_date_value,
                        "available_qty": pg_insert(table).excluded.available_qty,
                    },
                )
                connection.execute(stmt)

        return {"imported": len(rows), "message": f"已导入 {len(rows)} 条 {stock_date} 库存数据"}

    @staticmethod
    def _read_jst_stock_from_excel(jst_stock_root: Path, stock_date: str) -> dict:
        """Read product available stock from 聚水潭 daily stock Excel."""

        stock_dir = jst_stock_root / stock_date
        if not stock_dir.exists():
            return {}

        # Try common extensions
        candidates = []
        for ext in (".xlsx", ".xls", ".xlsm"):
            p = stock_dir / f"商品库存{ext}"
            if p.exists():
                candidates.append(p)

        stock_file = candidates[0] if candidates else None
        if stock_file is None:
            return {}

        wb = load_workbook(stock_file, data_only=True, read_only=True)
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb.active
        if ws is None:
            wb.close()
            return {}
        iterator = ws.iter_rows(values_only=True)
        header_row = next(iterator, None)
        if header_row is None:
            wb.close()
            return {}

        headers = [str(h).strip() if h else "" for h in header_row]

        # Find column indices for "商品编码" and "可用数"
        code_idx = None
        avail_idx = None
        for i, h in enumerate(headers):
            if "商品编码" in h or h == "商品编码":
                code_idx = i
            elif "可用数" in h or "可用库存" in h:
                avail_idx = i

        if code_idx is None or avail_idx is None:
            wb.close()
            return {}

        result = {}
        for row in iterator:
            code = str(row[code_idx]).strip() if code_idx < len(row) and row[code_idx] is not None else ""
            avail = row[avail_idx] if avail_idx < len(row) else None
            if code and avail is not None:
                try:
                    result[code] = int(float(str(avail)))
                except Exception:
                    result[code] = 0

        wb.close()
        return result

    def create_tables(self) -> None:
        with self.engine.begin() as connection:
            INVENTORY_TABLE.create(connection, checkfirst=True)
            INVENTORY_DETAIL_TABLE.create(connection, checkfirst=True)
            JST_STOCK_TABLE.create(connection, checkfirst=True)
            connection.execute(text("ALTER TABLE IF EXISTS inventory_records ADD COLUMN IF NOT EXISTS document_number TEXT"))
            self._backfill_document_numbers(connection)
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_document_number ON inventory_records (document_number)"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_records ADD COLUMN IF NOT EXISTS handler TEXT"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS color_barcode TEXT"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS color_name TEXT"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS size_quantities JSON"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code ON inventory_details (product_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code ON jst_daily_stock (product_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code_trgm ON inventory_details USING GIN (product_code gin_trgm_ops)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code_trgm ON jst_daily_stock USING GIN (product_code gin_trgm_ops)"))
            SUPPLIER_TABLE.create(connection, checkfirst=True)
            WAREHOUSE_TABLE.create(connection, checkfirst=True)
            self._ensure_supplier_schema(connection)
            self._sync_suppliers_from_gj(connection)
            GENERAL_CUSTOMER_BRAND_TABLE.create(connection, checkfirst=True)
            GENERAL_CUSTOMER_SHOP_TABLE.create(connection, checkfirst=True)
            self._seed_general_customer_shops(connection)

    @staticmethod
    def _ensure_supplier_schema(connection) -> None:
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS brand TEXT"))
        connection.execute(
            text(
                """
                DELETE FROM suppliers AS bad
                USING suppliers AS good
                WHERE bad.id <> good.id
                  AND bad.name = good.name
                  AND good.brand = CASE
                      WHEN upper(coalesce(bad.name, '')) LIKE '%TRUMPPIPE%'
                        OR coalesce(bad.name, '') LIKE '%烟斗%' THEN 'yandou'
                      WHEN upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
                        OR coalesce(bad.name, '') LIKE '%伊伴%' THEN 'eblan'
                      WHEN upper(coalesce(bad.name, '')) LIKE '%SMILEY%'
                        OR coalesce(bad.name, '') LIKE '%笑脸%'
                        OR coalesce(bad.name, '') LIKE '%小莲%' THEN 'smiley'
                      WHEN coalesce(bad.name, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
                      ELSE bad.brand
                  END
                  AND bad.brand IS DISTINCT FROM good.brand
                  AND (
                      upper(coalesce(bad.name, '')) LIKE '%TRUMPPIPE%'
                      OR coalesce(bad.name, '') LIKE '%烟斗%'
                      OR upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
                      OR coalesce(bad.name, '') LIKE '%伊伴%'
                      OR upper(coalesce(bad.name, '')) LIKE '%SMILEY%'
                      OR coalesce(bad.name, '') LIKE '%笑脸%'
                      OR coalesce(bad.name, '') LIKE '%小莲%'
                      OR coalesce(bad.name, '') LIKE '%千百度女鞋%'
                  )
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE suppliers
                SET brand = CASE
                    WHEN upper(coalesce(name, '')) LIKE '%TRUMPPIPE%'
                      OR coalesce(name, '') LIKE '%烟斗%' THEN 'yandou'
                    WHEN upper(coalesce(name, '')) LIKE '%EBLAN%'
                      OR coalesce(name, '') LIKE '%伊伴%' THEN 'eblan'
                    WHEN upper(coalesce(name, '')) LIKE '%SMILEY%'
                      OR coalesce(name, '') LIKE '%笑脸%'
                      OR coalesce(name, '') LIKE '%小莲%' THEN 'smiley'
                    WHEN coalesce(name, '') LIKE '%千百度品牌方%' THEN :default_brand
                    WHEN coalesce(name, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
                    WHEN coalesce(name, '') LIKE '%千百度%' THEN 'cbanner_mens'
                    ELSE :default_brand
                END
                WHERE brand IS NULL
                   OR brand = ''
                   OR (
                        upper(coalesce(name, '')) LIKE '%TRUMPPIPE%'
                        OR coalesce(name, '') LIKE '%烟斗%'
                        OR upper(coalesce(name, '')) LIKE '%EBLAN%'
                        OR coalesce(name, '') LIKE '%伊伴%'
                        OR upper(coalesce(name, '')) LIKE '%SMILEY%'
                        OR coalesce(name, '') LIKE '%笑脸%'
                        OR coalesce(name, '') LIKE '%小莲%'
                        OR coalesce(name, '') LIKE '%千百度女鞋%'
                   )
                """
            ),
            {"default_brand": CBANNER_MENS_BRAND},
        )
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ALTER COLUMN brand SET NOT NULL"))
        connection.execute(text("DROP INDEX IF EXISTS idx_suppliers_brand"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_suppliers_brand ON suppliers (brand)"))
        connection.execute(
            text(
                """
                do $$
                begin
                    if exists (
                        select 1
                        from pg_constraint
                        where conname = 'uq_supplier_name'
                    ) then
                        alter table suppliers drop constraint uq_supplier_name;
                    end if;
                end $$;
                """
            )
        )
        connection.execute(
            text(
                """
                do $$
                begin
                    if not exists (
                        select 1
                        from pg_constraint
                        where conname = 'uq_supplier_brand_name'
                    ) then
                        alter table suppliers add constraint uq_supplier_brand_name unique (brand, name);
                    end if;
                end $$;
                """
            )
        )

    @staticmethod
    def _sync_suppliers_from_gj(connection) -> int:
        if not inspect(connection).has_table(GJ_MERGED_PRODUCT_INFO_TABLE.name):
            return 0
        synced = 0
        rows = connection.execute(
            select(
                GJ_MERGED_PRODUCT_INFO_TABLE.c.fine_table_brand,
                GJ_MERGED_PRODUCT_INFO_TABLE.c.primary_supplier,
            )
            .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.fine_table_brand.in_(GJ_FINE_TABLE_BRANDS))
            .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.primary_supplier.isnot(None))
            .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.primary_supplier != "")
            .distinct()
        ).mappings()
        for row in rows:
            name = str(row["primary_supplier"] or "").strip()
            brand = infer_supplier_brand_from_name(name) or str(row["fine_table_brand"] or "").strip()
            if not brand or not name:
                continue
            exists = connection.execute(
                select(SUPPLIER_TABLE.c.id).where(
                    SUPPLIER_TABLE.c.brand == brand,
                    SUPPLIER_TABLE.c.name == name,
                )
            ).first()
            if exists is None:
                connection.execute(insert(SUPPLIER_TABLE).values(brand=brand, name=name))
                synced += 1
        return synced

    def _seed_general_customer_shops(self, connection) -> None:
        defaults = [
            {"customer_name": "烟斗", "shop_name": "烟斗唯品会店铺"},
        ]
        for row in defaults:
            self._ensure_general_customer_brand(connection, row["customer_name"])
            exists = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.id).where(
                    GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == row["customer_name"],
                    GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name == row["shop_name"],
                )
            ).first()
            if exists is None:
                connection.execute(insert(GENERAL_CUSTOMER_SHOP_TABLE).values(**row))

        existing_brands = connection.execute(select(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name).distinct()).all()
        for row in existing_brands:
            self._ensure_general_customer_brand(connection, row[0])

    @staticmethod
    def _ensure_general_customer_brand(connection, name: str) -> None:
        if not name:
            return
        exists = connection.execute(
            select(GENERAL_CUSTOMER_BRAND_TABLE.c.id).where(GENERAL_CUSTOMER_BRAND_TABLE.c.name == name)
        ).first()
        if exists is None:
            connection.execute(insert(GENERAL_CUSTOMER_BRAND_TABLE).values(name=name))

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _coerce_empty(data: Mapping[str, object]) -> dict[str, object]:
        return {k: (None if v == "" else v) for k, v in data.items()}

    @staticmethod
    def _prepare_record(record: Mapping[str, object]) -> dict[str, object]:
        payload = {}
        for key, value in record.items():
            if value == "":
                payload[key] = None
            else:
                payload[key] = value
        if "date" in payload and "date_value" not in payload:
            payload["date_value"] = parse_date(payload.get("date"))
        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            payload["raw_payload"] = {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in raw_payload.items()
            }
        return payload

    @staticmethod
    def _generate_document_number(connection, date_value: object) -> str:
        parsed_date = date_value if isinstance(date_value, date) else parse_date(date_value)
        date_text = (parsed_date or date.today()).strftime("%Y-%m-%d")
        alphabet = string.ascii_uppercase
        for _ in range(100):
            prefix = "".join(secrets.choice(alphabet) for _ in range(5))
            suffix = f"{secrets.randbelow(10000):04d}"
            document_number = f"{prefix}-{date_text}-{suffix}"
            exists = connection.execute(
                select(INVENTORY_TABLE.c.id).where(INVENTORY_TABLE.c.document_number == document_number)
            ).first()
            if exists is None:
                return document_number
        raise RuntimeError("Failed to generate unique inventory document number")

    @staticmethod
    def _backfill_document_numbers(connection) -> None:
        rows = connection.execute(
            select(
                INVENTORY_TABLE.c.id,
                INVENTORY_TABLE.c.date,
                INVENTORY_TABLE.c.date_value,
            ).where(or_(
                INVENTORY_TABLE.c.document_number.is_(None),
                INVENTORY_TABLE.c.document_number == "",
            ))
        ).mappings()
        for row in rows:
            document_number = InventoryRepository._generate_document_number(
                connection,
                row.get("date_value") or row.get("date"),
            )
            connection.execute(
                update(INVENTORY_TABLE)
                .where(INVENTORY_TABLE.c.id == row["id"])
                .values(document_number=document_number)
            )

    @staticmethod
    def _prepare_supplier(data: Mapping[str, object]) -> dict[str, object]:
        name = str(data.get("name") or "").strip()
        brand = infer_supplier_brand_from_name(name) or str(data.get("brand") or "").strip() or CBANNER_MENS_BRAND
        payload = {
            "brand": brand,
            "name": name,
            "factory_code": str(data.get("factory_code") or "").strip() or None,
            "contact": str(data.get("contact") or "").strip() or None,
            "address": str(data.get("address") or "").strip() or None,
            "notes": str(data.get("notes") or "").strip() or None,
        }
        if payload["brand"] not in GJ_FINE_TABLE_BRANDS:
            payload["brand"] = CBANNER_MENS_BRAND
        return payload
