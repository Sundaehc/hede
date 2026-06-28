from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal

from pathlib import Path

import orjson
from openpyxl import load_workbook
from sqlalchemy import and_, case, create_engine, delete, desc, func, insert, inspect, or_, select, text, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_schema import GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, INVENTORY_ACCOUNT_SUBJECT_TABLE, INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, JST_STOCK_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE
from domain.inventory_sources import ACCOUNTING_DOCUMENT_TYPES
from domain.gj_brand import CBANNER_MENS_BRAND, GJ_FINE_TABLE_BRANDS, SUPPLIER_BRANDS, infer_supplier_brand_from_name
from domain.vip_schema import JST_MONTHLY_ORDERS_TABLE, JST_SIZE_STOCK_TABLE, VIP_DAILY_TABLE
from storage.date_normalization import parse_date, parse_month_day


DOCUMENT_NUMBER_PREFIXES = {
    "进货订单": "JHDD",
    "进货单": "JHD",
    "进货退货单": "JHTHD",
    "报溢单": "BYD",
    "报损单": "BSD",
    "批发销售单": "PFXSD",
    "批发销售退货单": "PFXSTHD",
    "同价调拨单": "TJDBD",
    "应付款减少": "YFKJS",
    "应付款增加": "YFKZJ",
    "应收款减少": "YSKJS",
    "应收款增加": "YSKZJ",
}
DEFAULT_DOCUMENT_NUMBER_PREFIX = "DJ"
SUPPLIER_RATING_CACHE_TTL_SECONDS = 600

SUPPLIER_LEDGER_INCREASE_TYPES = ("进货单", "应付款增加")
SUPPLIER_LEDGER_DECREASE_TYPES = ("进货退货单", "应付款减少")
SUPPLIER_LEDGER_NEUTRAL_TYPES = ("同价调拨单",)
CUSTOMER_LEDGER_INCREASE_TYPES = ("批发销售单", "应收款增加")
CUSTOMER_LEDGER_DECREASE_TYPES = ("批发销售退货单", "应收款减少")


def _json_serializer(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


class InventoryRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )
        self._supplier_rating_metrics_cache: dict[str, tuple[datetime, dict[str, dict[str, object]]]] = {}
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
        exclude_document_type: str | None = None,
        summary: str | None = None,
        original_sku: str | None = None,
        product_code: str | None = None,
        handler: str | None = None,
        completion_status: str | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        table = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        stock = JST_STOCK_TABLE
        count_statement = select(func.count()).select_from(table)
        items_statement = select(table)

        self.purge_expired_deleted_records()
        conditions = [table.c.deleted_at.is_(None)]
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
        if exclude_document_type:
            conditions.append(or_(table.c.document_type.is_(None), table.c.document_type != exclude_document_type))
        if summary:
            conditions.append(table.c.summary.ilike(f"%{summary.strip()}%"))
        if handler:
            conditions.append(table.c.handler.ilike(f"%{handler.strip()}%"))
        if completion_status == "incomplete":
            is_accounting_document = table.c.document_type.in_(ACCOUNTING_DOCUMENT_TYPES)
            is_product_document = or_(table.c.document_type.is_(None), ~is_accounting_document)
            conditions.append(or_(
                ~select(detail.c.id)
                .where(detail.c.document_id == table.c.id)
                .exists(),
                and_(
                    is_accounting_document,
                    select(detail.c.id)
                    .where(
                        detail.c.document_id == table.c.id,
                        or_(
                            detail.c.amount.is_(None),
                            detail.c.amount == 0,
                        ),
                    )
                    .exists(),
                ),
                and_(
                    is_product_document,
                    select(detail.c.id)
                    .where(
                        detail.c.document_id == table.c.id,
                        or_(
                            detail.c.unit_price.is_(None),
                            detail.c.unit_price == 0,
                        ),
                    )
                    .exists(),
                ),
            ))
        elif completion_status == "completed":
            is_accounting_document = table.c.document_type.in_(ACCOUNTING_DOCUMENT_TYPES)
            is_product_document = or_(table.c.document_type.is_(None), ~is_accounting_document)
            conditions.append(
                select(detail.c.id)
                .where(detail.c.document_id == table.c.id)
                .exists()
            )
            conditions.append(or_(
                and_(
                    is_accounting_document,
                    ~select(detail.c.id)
                    .where(
                        detail.c.document_id == table.c.id,
                        or_(
                            detail.c.amount.is_(None),
                            detail.c.amount == 0,
                        ),
                    )
                    .exists(),
                ),
                and_(
                    is_product_document,
                    ~select(detail.c.id)
                    .where(
                        detail.c.document_id == table.c.id,
                        or_(
                            detail.c.unit_price.is_(None),
                            detail.c.unit_price == 0,
                        ),
                    )
                    .exists(),
                ),
            )
            )
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
        for item in items:
            self._clear_accounting_record_summary(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_record(self, record_id: int) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        statement = select(table).where(table.c.id == record_id, table.c.deleted_at.is_(None))
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_record_by_summary(self, summary: str) -> dict[str, object] | None:
        normalized_summary = str(summary or "").strip()
        if not normalized_summary:
            return None
        table = INVENTORY_TABLE
        statement = select(table).where(table.c.summary == normalized_summary).order_by(desc(table.c.id))
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def create_record(self, record: Mapping[str, object]) -> dict[str, object]:
        table = INVENTORY_TABLE
        with self.engine.begin() as connection:
            payload = self._prepare_record(record)
            if not payload.get("document_number"):
                payload["document_number"] = self._generate_document_number(
                    connection,
                    payload.get("date_value") or payload.get("date"),
                    payload.get("document_type"),
                )
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
        statement = (
            update(table)
            .where(table.c.id == record_id, table.c.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def delete_records(self, ids: list[int]) -> int:
        if not ids:
            return 0
        table = INVENTORY_TABLE
        statement = (
            update(table)
            .where(table.c.id.in_(ids), table.c.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount

    def list_deleted_records(
        self,
        *,
        page: int,
        page_size: int,
        document_type: str | None = None,
        exclude_document_type: str | None = None,
    ) -> dict[str, object]:
        self.purge_expired_deleted_records()
        table = INVENTORY_TABLE
        conditions = [table.c.deleted_at.isnot(None)]
        if document_type:
            conditions.append(table.c.document_type == document_type)
        if exclude_document_type:
            conditions.append(or_(table.c.document_type.is_(None), table.c.document_type != exclude_document_type))
        criterion = and_(*conditions)
        count_statement = select(func.count()).select_from(table).where(criterion)
        items_statement = (
            select(table)
            .where(criterion)
            .order_by(desc(table.c.deleted_at), desc(table.c.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]
        for item in items:
            self._clear_accounting_record_summary(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def restore_record(self, record_id: int) -> dict[str, object] | None:
        self.purge_expired_deleted_records()
        table = INVENTORY_TABLE
        statement = (
            update(table)
            .where(table.c.id == record_id, table.c.deleted_at.isnot(None))
            .values(deleted_at=None)
            .returning(table)
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def restore_records(self, ids: list[int]) -> int:
        self.purge_expired_deleted_records()
        if not ids:
            return 0
        table = INVENTORY_TABLE
        statement = (
            update(table)
            .where(table.c.id.in_(ids), table.c.deleted_at.isnot(None))
            .values(deleted_at=None)
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount or 0

    def permanently_delete_records(self, ids: list[int]) -> int:
        self.purge_expired_deleted_records()
        if not ids:
            return 0
        table = INVENTORY_TABLE
        statement = delete(table).where(table.c.id.in_(ids), table.c.deleted_at.isnot(None))
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount or 0

    def purge_expired_deleted_records(self) -> int:
        table = INVENTORY_TABLE
        statement = delete(table).where(table.c.deleted_at < func.now() - text("interval '10 days'"))
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount or 0

    def get_counterparty_ledger(
        self,
        *,
        counterparty_type: str,
        name: str,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> dict[str, object]:
        table = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        normalized_name = str(name or "").strip()
        if counterparty_type == "customer":
            increase_types = CUSTOMER_LEDGER_INCREASE_TYPES
            decrease_types = CUSTOMER_LEDGER_DECREASE_TYPES
            neutral_types: tuple[str, ...] = ()
        else:
            increase_types = SUPPLIER_LEDGER_INCREASE_TYPES
            decrease_types = SUPPLIER_LEDGER_DECREASE_TYPES
            neutral_types = SUPPLIER_LEDGER_NEUTRAL_TYPES
        document_types = (*increase_types, *decrease_types, *neutral_types)

        detail_amount = (
            select(
                detail.c.document_id.label("document_id"),
                func.coalesce(func.sum(detail.c.amount), 0).label("detail_amount"),
            )
            .group_by(detail.c.document_id)
            .subquery()
        )
        effective_amount = func.coalesce(detail_amount.c.detail_amount, table.c.amount, 0)
        base_conditions = [
            table.c.deleted_at.is_(None),
            table.c.supplier == normalized_name,
            table.c.document_type.in_(document_types),
        ]

        start_date = parse_date(date_start) if date_start else None
        end_date = parse_date(date_end) if date_end else None
        range_conditions = list(base_conditions)
        if date_start:
            range_conditions.append(table.c.date_value >= start_date if start_date else table.c.date >= date_start)
        if date_end:
            range_conditions.append(table.c.date_value <= end_date if end_date else table.c.date <= date_end)

        increase_expr = case(
            (table.c.document_type.in_(increase_types), effective_amount),
            else_=0,
        )
        decrease_expr = case(
            (table.c.document_type.in_(decrease_types), effective_amount),
            else_=0,
        )

        items_statement = (
            select(
                table.c.id,
                table.c.document_number,
                table.c.date,
                table.c.document_type,
                table.c.summary,
                table.c.handler,
                table.c.warehouse,
                increase_expr.label("increase_amount"),
                decrease_expr.label("decrease_amount"),
            )
            .outerjoin(detail_amount, detail_amount.c.document_id == table.c.id)
            .where(and_(*range_conditions))
            .order_by(table.c.date_value.nulls_last(), table.c.date, table.c.id)
        )
        totals_statement = (
            select(
                func.coalesce(func.sum(increase_expr), 0).label("increase_total"),
                func.coalesce(func.sum(decrease_expr), 0).label("decrease_total"),
            )
            .select_from(table)
            .outerjoin(detail_amount, detail_amount.c.document_id == table.c.id)
            .where(and_(*range_conditions))
        )

        beginning_balance = Decimal("0")
        if date_start:
            beginning_conditions = list(base_conditions)
            beginning_conditions.append(table.c.date_value < start_date if start_date else table.c.date < date_start)
            beginning_statement = (
                select(func.coalesce(func.sum(increase_expr - decrease_expr), 0))
                .select_from(table)
                .outerjoin(detail_amount, detail_amount.c.document_id == table.c.id)
                .where(and_(*beginning_conditions))
            )
        else:
            beginning_statement = None

        with self.engine.connect() as connection:
            if beginning_statement is not None:
                beginning_balance = Decimal(str(connection.execute(beginning_statement).scalar_one() or "0"))
            totals = connection.execute(totals_statement).mappings().one()
            rows = [dict(row) for row in connection.execute(items_statement).mappings()]

        running_balance = beginning_balance
        items: list[dict[str, object]] = []
        for index, row in enumerate(rows, start=1):
            increase = Decimal(str(row.pop("increase_amount") or "0"))
            decrease = Decimal(str(row.pop("decrease_amount") or "0"))
            running_balance = running_balance + increase - decrease
            items.append({
                **row,
                "row_number": index,
                "increase_amount": self._format_decimal(increase) if increase else "",
                "decrease_amount": self._format_decimal(decrease) if decrease else "",
                "balance": self._format_decimal(running_balance),
            })

        increase_total = Decimal(str(totals.get("increase_total") or "0"))
        decrease_total = Decimal(str(totals.get("decrease_total") or "0"))
        ending_balance = beginning_balance + increase_total - decrease_total
        return {
            "items": items,
            "counterparty_type": counterparty_type,
            "name": normalized_name,
            "date_start": date_start,
            "date_end": date_end,
            "beginning_balance": self._format_decimal(beginning_balance),
            "increase_total": self._format_decimal(increase_total),
            "decrease_total": self._format_decimal(decrease_total),
            "ending_balance": self._format_decimal(ending_balance),
        }

    # ── Suppliers ──────────────────────────────────────────────────

    def list_suppliers(self, *, brand: str | None = None) -> list[dict[str, object]]:
        statement = select(SUPPLIER_TABLE).order_by(SUPPLIER_TABLE.c.brand, SUPPLIER_TABLE.c.id)
        if brand:
            statement = statement.where(SUPPLIER_TABLE.c.brand == brand)
        with self.engine.begin() as connection:
            items = [dict(row) for row in connection.execute(statement).mappings()]
            self._attach_supplier_ratings(connection, items)
            return items

    def list_suppliers_page(
        self,
        *,
        page: int,
        page_size: int,
        query: str | None = None,
        brand: str | None = None,
        sort: str | None = None,
    ) -> dict[str, object]:
        count_statement = select(func.count()).select_from(SUPPLIER_TABLE)
        sort = (sort or "").strip()
        items_statement = (
            select(SUPPLIER_TABLE)
            .order_by(SUPPLIER_TABLE.c.id)
        )
        sort_by_grade = sort in {"grade_asc", "grade_desc"}
        if not sort_by_grade:
            items_statement = items_statement.offset((page - 1) * page_size).limit(page_size)
        conditions = []
        if brand:
            conditions.append(SUPPLIER_TABLE.c.brand == brand)
        normalized_query = (query or "").strip()
        if normalized_query:
            like = f"%{normalized_query}%"
            conditions.append(or_(
                SUPPLIER_TABLE.c.name.ilike(like),
                SUPPLIER_TABLE.c.factory_code.ilike(like),
                SUPPLIER_TABLE.c.contact.ilike(like),
                SUPPLIER_TABLE.c.wechat.ilike(like),
            ))
        if conditions:
            criterion = conditions[0] if len(conditions) == 1 else and_(*conditions)
            count_statement = count_statement.where(criterion)
            items_statement = items_statement.where(criterion)
        with self.engine.begin() as connection:
            total = connection.execute(count_statement).scalar_one()
            if sort_by_grade:
                missing_statement = select(func.count()).select_from(SUPPLIER_TABLE).where(or_(
                    SUPPLIER_TABLE.c.factory_grade.is_(None),
                    SUPPLIER_TABLE.c.factory_grade == "",
                    SUPPLIER_TABLE.c.factory_suggestion.is_(None),
                    SUPPLIER_TABLE.c.factory_suggestion == "",
                ))
                if conditions:
                    missing_statement = missing_statement.where(criterion)
                missing_count = connection.execute(missing_statement).scalar_one()
                if missing_count == 0:
                    grade_order_expr = case(
                        (SUPPLIER_TABLE.c.factory_grade == ("A" if sort == "grade_asc" else "D"), 0),
                        (SUPPLIER_TABLE.c.factory_grade == ("B" if sort == "grade_asc" else "C"), 1),
                        (SUPPLIER_TABLE.c.factory_grade == ("C" if sort == "grade_asc" else "B"), 2),
                        (SUPPLIER_TABLE.c.factory_grade == ("D" if sort == "grade_asc" else "A"), 3),
                        else_=99,
                    )
                    sorted_statement = (
                        select(SUPPLIER_TABLE)
                        .order_by(grade_order_expr, SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.id)
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                    if conditions:
                        sorted_statement = sorted_statement.where(criterion)
                    items = [dict(row) for row in connection.execute(sorted_statement).mappings()]
                else:
                    items = [dict(row) for row in connection.execute(items_statement).mappings()]
                    self._attach_supplier_ratings(connection, items, use_cache=True)
                    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3} if sort == "grade_asc" else {"D": 0, "C": 1, "B": 2, "A": 3}
                    items.sort(
                        key=lambda item: (
                            grade_order.get(str(item.get("factory_grade") or ""), 99),
                            str(item.get("name") or ""),
                            int(item.get("id") or 0),
                        ),
                    )
                    start = (page - 1) * page_size
                    items = items[start:start + page_size]
            else:
                items = [dict(row) for row in connection.execute(items_statement).mappings()]
                self._attach_supplier_ratings(connection, items)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _attach_supplier_ratings(self, connection, items: list[dict[str, object]], *, use_cache: bool = False) -> None:
        supplier_names = [str(item.get("name") or "").strip() for item in items if str(item.get("name") or "").strip()]
        if not supplier_names or not inspect(connection).has_table(GJ_MERGED_PRODUCT_INFO_TABLE.name):
            for item in items:
                grade, suggestion = InventoryRepository._supplier_grade_and_suggestion(item, {})
                item["factory_grade"] = grade
                item["factory_suggestion"] = suggestion
            self._persist_supplier_ratings(connection, items)
            return

        cache_key = "\n".join(sorted(set(supplier_names)))
        if use_cache:
            cached = self._supplier_rating_metrics_cache.get(cache_key)
            if cached is not None:
                cached_at, cached_metrics = cached
                if (datetime.now() - cached_at).total_seconds() < SUPPLIER_RATING_CACHE_TTL_SECONDS:
                    for item in items:
                        supplier = str(item.get("name") or "").strip()
                        metrics = dict(cached_metrics.get(supplier, {}))
                        rates = metrics.get("reject_rate_values") or []
                        metrics["reject_rate"] = sum(rates) / len(rates) if rates else None
                        grade, suggestion = InventoryRepository._supplier_grade_and_suggestion(item, metrics)
                        item["factory_grade"] = grade
                        item["factory_suggestion"] = suggestion
                    self._persist_supplier_ratings(connection, items)
                    return

        latest_gj_date = connection.execute(select(func.max(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value))).scalar()
        gj_conditions = [
            GJ_MERGED_PRODUCT_INFO_TABLE.c.primary_supplier.in_(supplier_names),
            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code.isnot(None),
            GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code != "",
        ]
        if latest_gj_date is not None:
            gj_conditions.append(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value == latest_gj_date)

        product_rows = list(connection.execute(
            select(
                GJ_MERGED_PRODUCT_INFO_TABLE.c.primary_supplier,
                GJ_MERGED_PRODUCT_INFO_TABLE.c.goods_code,
                GJ_MERGED_PRODUCT_INFO_TABLE.c.original_goods_code,
            )
            .where(and_(*gj_conditions))
        ).mappings())

        metrics_by_supplier: dict[str, dict[str, object]] = {
            name: {
                "product_codes": set(),
                "original_codes": set(),
                "style_count": 0,
                "sales_30d": 0,
                "stock_qty": 0,
                "reject_count": 0,
                "reject_rate_values": [],
            }
            for name in supplier_names
        }
        supplier_by_code: dict[str, set[str]] = {}
        for row in product_rows:
            supplier = str(row.get("primary_supplier") or "").strip()
            code = str(row.get("goods_code") or "").strip()
            original_code = str(row.get("original_goods_code") or "").strip()
            if not supplier or not code:
                continue
            bucket = metrics_by_supplier.setdefault(supplier, {
                "product_codes": set(),
                "original_codes": set(),
                "style_count": 0,
                "sales_30d": 0,
                "stock_qty": 0,
                "reject_count": 0,
                "reject_rate_values": [],
            })
            bucket["product_codes"].add(code)
            if original_code:
                bucket["original_codes"].add(original_code)
            supplier_by_code.setdefault(code, set()).add(supplier)

        for bucket in metrics_by_supplier.values():
            bucket["style_count"] = len(bucket["original_codes"] or bucket["product_codes"])

        product_codes = sorted(supplier_by_code)
        if product_codes:
            if inspect(connection).has_table(VIP_DAILY_TABLE.name):
                daily_rows = connection.execute(
                    select(
                        VIP_DAILY_TABLE.c.goods_code,
                        func.max(VIP_DAILY_TABLE.c.sales_volume).label("sales_volume"),
                        func.max(VIP_DAILY_TABLE.c.reject_count).label("reject_count"),
                        func.max(VIP_DAILY_TABLE.c.reject_rate).label("reject_rate"),
                    )
                    .where(VIP_DAILY_TABLE.c.goods_code.in_(product_codes))
                    .where(VIP_DAILY_TABLE.c.period == "30d")
                    .group_by(VIP_DAILY_TABLE.c.goods_code)
                ).mappings()
                for row in daily_rows:
                    code = str(row.get("goods_code") or "").strip()
                    for supplier in supplier_by_code.get(code, ()):
                        bucket = metrics_by_supplier[supplier]
                        bucket["sales_30d"] = int(bucket["sales_30d"]) + InventoryRepository._to_int(row.get("sales_volume"))
                        bucket["reject_count"] = int(bucket["reject_count"]) + InventoryRepository._to_int(row.get("reject_count"))
                        reject_rate = InventoryRepository._percent_to_float(row.get("reject_rate"))
                        if reject_rate is not None:
                            bucket["reject_rate_values"].append(reject_rate)

            if inspect(connection).has_table(JST_MONTHLY_ORDERS_TABLE.name):
                max_order_time = connection.execute(select(func.max(JST_MONTHLY_ORDERS_TABLE.c.order_time_at))).scalar()
                if max_order_time is not None:
                    start_time = max_order_time - timedelta(days=30)
                    order_rows = connection.execute(
                        select(
                            JST_MONTHLY_ORDERS_TABLE.c.style_code,
                            func.sum(JST_MONTHLY_ORDERS_TABLE.c.quantity).label("quantity"),
                        )
                        .where(JST_MONTHLY_ORDERS_TABLE.c.style_code.in_(product_codes))
                        .where(JST_MONTHLY_ORDERS_TABLE.c.order_time_at >= start_time)
                        .where(JST_MONTHLY_ORDERS_TABLE.c.order_time_at <= max_order_time)
                        .group_by(JST_MONTHLY_ORDERS_TABLE.c.style_code)
                    ).mappings()
                    for row in order_rows:
                        code = str(row.get("style_code") or "").strip()
                        for supplier in supplier_by_code.get(code, ()):
                            bucket = metrics_by_supplier[supplier]
                            bucket["sales_30d"] = int(bucket["sales_30d"]) + InventoryRepository._to_int(row.get("quantity"))

            if inspect(connection).has_table(JST_SIZE_STOCK_TABLE.name):
                stock_rows = connection.execute(
                    select(
                        JST_SIZE_STOCK_TABLE.c.product_code,
                        func.sum(JST_SIZE_STOCK_TABLE.c.stock_qty).label("stock_qty"),
                    )
                    .where(JST_SIZE_STOCK_TABLE.c.product_code.in_(product_codes))
                    .group_by(JST_SIZE_STOCK_TABLE.c.product_code)
                ).mappings()
                for row in stock_rows:
                    code = str(row.get("product_code") or "").strip()
                    for supplier in supplier_by_code.get(code, ()):
                        bucket = metrics_by_supplier[supplier]
                        bucket["stock_qty"] = int(bucket["stock_qty"]) + InventoryRepository._to_int(row.get("stock_qty"))

        for item in items:
            supplier = str(item.get("name") or "").strip()
            metrics = metrics_by_supplier.get(supplier, {})
            rates = metrics.get("reject_rate_values") or []
            metrics["reject_rate"] = sum(rates) / len(rates) if rates else None
            grade, suggestion = InventoryRepository._supplier_grade_and_suggestion(item, metrics)
            item["factory_grade"] = grade
            item["factory_suggestion"] = suggestion

        self._persist_supplier_ratings(connection, items)

        if use_cache:
            self._supplier_rating_metrics_cache[cache_key] = (datetime.now(), metrics_by_supplier)

    @staticmethod
    def _persist_supplier_ratings(connection, items: list[dict[str, object]]) -> None:
        for item in items:
            supplier_id = item.get("id")
            grade = item.get("factory_grade")
            suggestion = item.get("factory_suggestion")
            if not supplier_id:
                continue
            connection.execute(
                update(SUPPLIER_TABLE)
                .where(SUPPLIER_TABLE.c.id == supplier_id)
                .where(or_(
                    SUPPLIER_TABLE.c.factory_grade.is_distinct_from(grade),
                    SUPPLIER_TABLE.c.factory_suggestion.is_distinct_from(suggestion),
                ))
                .values(factory_grade=grade, factory_suggestion=suggestion)
            )

    @staticmethod
    def _supplier_grade_and_suggestion(item: Mapping[str, object], metrics: Mapping[str, object]) -> tuple[str, str]:
        status = str(item.get("cooperation_status") or "").strip()
        if status in {"淘汰", "暂停"}:
            return "D", "暂停合作，停止开发新款。"

        style_count = InventoryRepository._to_int(metrics.get("style_count"))
        sales_30d = InventoryRepository._to_int(metrics.get("sales_30d"))
        stock_qty = InventoryRepository._to_int(metrics.get("stock_qty"))
        reject_rate_raw = metrics.get("reject_rate")
        reject_rate = float(reject_rate_raw) if reject_rate_raw is not None else None
        sell_through = sales_30d / (sales_30d + stock_qty) if sales_30d + stock_qty > 0 else 0

        if style_count == 0:
            return "C", "暂无有效款式数据，先观察维护资料。"
        if sales_30d <= 0 and stock_qty >= 300:
            return "D", "库存有压力且近期无销售，建议暂停新款开发。"
        if (reject_rate is not None and reject_rate >= 0.18) or (stock_qty >= 1000 and sell_through < 0.1):
            return "C", "库存或退货风险偏高，建议限制下单并观察整改。"
        if sales_30d >= 500 and sell_through >= 0.35 and (reject_rate is None or reject_rate < 0.08):
            return "A", "重点合作，优先开发，优先下单。"
        if sales_30d >= 100 and sell_through >= 0.15 and (reject_rate is None or reject_rate < 0.15):
            return "B", "保持合作，继续观察。"
        return "C", "销售表现一般，建议控制节奏继续观察。"

    @staticmethod
    def _to_int(value: object) -> int:
        if value in (None, ""):
            return 0
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _percent_to_float(value: object) -> float | None:
        if value in (None, ""):
            return None
        text_value = str(value).strip().replace(",", "")
        try:
            if text_value.endswith("%"):
                return float(text_value[:-1]) / 100
            parsed = float(text_value)
            return parsed / 100 if parsed > 1 else parsed
        except ValueError:
            return None

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

    # ── Inventory Account Subjects ─────────────────────────────────

    def list_account_subjects(self) -> list[dict[str, object]]:
        statement = select(INVENTORY_ACCOUNT_SUBJECT_TABLE).order_by(
            INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id,
            INVENTORY_ACCOUNT_SUBJECT_TABLE.c.name,
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_account_subject(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "code": str(data.get("code") or "").strip() or None,
            "name": str(data.get("name") or "").strip(),
        }
        statement = insert(INVENTORY_ACCOUNT_SUBJECT_TABLE).values(**payload).returning(INVENTORY_ACCOUNT_SUBJECT_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def delete_account_subject(self, subject_id: int) -> bool:
        statement = delete(INVENTORY_ACCOUNT_SUBJECT_TABLE).where(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id == subject_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

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
        payload = self._filter_table_payload(table, self._coerce_empty(data))
        statement = insert(table).values(**payload).returning(table)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        self.recalculate_totals(payload.get("document_id"))
        return dict(row)

    def create_details(self, rows: list[Mapping[str, object]], document_id: object) -> int:
        if not rows:
            return 0
        table = INVENTORY_DETAIL_TABLE
        payload = [self._filter_table_payload(table, self._coerce_empty(row)) for row in rows]
        with self.engine.begin() as connection:
            result = connection.execute(insert(table), payload)
        self.recalculate_totals(document_id)
        return result.rowcount if result.rowcount and result.rowcount > 0 else len(payload)

    def replace_details(self, document_id: object, rows: list[Mapping[str, object]]) -> int:
        table = INVENTORY_DETAIL_TABLE
        payload = []
        for row in rows:
            item = self._filter_table_payload(table, self._coerce_empty(row))
            item["document_id"] = document_id
            payload.append(item)
        with self.engine.begin() as connection:
            connection.execute(delete(table).where(table.c.document_id == document_id))
            result = connection.execute(insert(table), payload) if payload else None
        self.recalculate_totals(document_id)
        if result is None:
            return 0
        return result.rowcount if result.rowcount and result.rowcount > 0 else len(payload)

    def update_detail(self, detail_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        table = INVENTORY_DETAIL_TABLE
        payload = self._filter_table_payload(table, self._coerce_empty(data))
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

    def delete_details(self, document_id: object, detail_ids: list[int]) -> int:
        if not detail_ids:
            return 0
        table = INVENTORY_DETAIL_TABLE
        statement = delete(table).where(
            table.c.document_id == document_id,
            table.c.id.in_(detail_ids),
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        deleted = result.rowcount or 0
        if deleted > 0:
            self.recalculate_totals(document_id)
        return deleted

    def recalculate_totals(self, document_id: object) -> None:
        detail = INVENTORY_DETAIL_TABLE
        record = INVENTORY_TABLE
        with self.engine.connect() as connection:
            document_type = connection.execute(
                select(record.c.document_type).where(record.c.id == document_id)
            ).scalar_one_or_none()
            if document_type in ACCOUNTING_DOCUMENT_TYPES:
                total_count = None
                amount = None
            else:
                stmt = select(
                    func.coalesce(func.sum(detail.c.quantity), 0),
                    func.coalesce(func.sum(detail.c.amount), 0),
                ).where(detail.c.document_id == document_id)
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
            connection.execute(text("ALTER TABLE IF EXISTS inventory_records ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_deleted_at ON inventory_records (deleted_at)"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS color_barcode TEXT"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS color_name TEXT"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS size_quantities JSON"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS remark TEXT"))
            connection.execute(text("ALTER TABLE IF EXISTS inventory_details ADD COLUMN IF NOT EXISTS extra_fields JSON"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code ON inventory_details (product_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code ON jst_daily_stock (product_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code_trgm ON inventory_details USING GIN (product_code gin_trgm_ops)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code_trgm ON jst_daily_stock USING GIN (product_code gin_trgm_ops)"))
            INVENTORY_ACCOUNT_SUBJECT_TABLE.create(connection, checkfirst=True)
            self._seed_account_subjects(connection)
            SUPPLIER_TABLE.create(connection, checkfirst=True)
            WAREHOUSE_TABLE.create(connection, checkfirst=True)
            self._ensure_supplier_schema(connection)
            self._sync_suppliers_from_gj(connection)
            GENERAL_CUSTOMER_BRAND_TABLE.create(connection, checkfirst=True)
            GENERAL_CUSTOMER_SHOP_TABLE.create(connection, checkfirst=True)
            self._seed_general_customer_shops(connection)
            connection.execute(text("UPDATE inventory_records SET total_count = NULL, amount = NULL, warehouse = NULL WHERE document_type IN ('应付款减少', '应付款增加', '应收款减少', '应收款增加') AND (total_count IS NOT NULL OR amount IS NOT NULL OR warehouse IS NOT NULL)"))
            connection.execute(text("DELETE FROM inventory_records WHERE deleted_at < now() - interval '10 days'"))

    @staticmethod
    def _seed_account_subjects(connection) -> None:
        defaults = [
            {"code": "0337", "name": "罚款收入"},
            {"code": None, "name": "付货款"},
        ]
        for row in defaults:
            exists = connection.execute(
                select(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id).where(
                    INVENTORY_ACCOUNT_SUBJECT_TABLE.c.name == row["name"]
                )
            ).first()
            if exists is None:
                connection.execute(insert(INVENTORY_ACCOUNT_SUBJECT_TABLE).values(**row))

    @staticmethod
    def _ensure_supplier_schema(connection) -> None:
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS brand TEXT"))
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS wechat TEXT"))
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS cooperation_status TEXT"))
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS factory_grade TEXT"))
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ADD COLUMN IF NOT EXISTS factory_suggestion TEXT"))
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
                      WHEN upper(coalesce(bad.name, '')) LIKE '%NIKE%'
                        OR upper(coalesce(bad.name, '')) ~ '(^|[^A-Z0-9])NI([^A-Z0-9]|$)'
                        OR coalesce(bad.name, '') LIKE '%耐克%' THEN 'ni'
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
                      OR upper(coalesce(bad.name, '')) LIKE '%NIKE%'
                      OR upper(coalesce(bad.name, '')) ~ '(^|[^A-Z0-9])NI([^A-Z0-9]|$)'
                      OR coalesce(bad.name, '') LIKE '%耐克%'
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
                    WHEN upper(coalesce(name, '')) LIKE '%NIKE%'
                      OR upper(coalesce(name, '')) ~ '(^|[^A-Z0-9])NI([^A-Z0-9]|$)'
                      OR coalesce(name, '') LIKE '%耐克%' THEN 'ni'
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
                        OR upper(coalesce(name, '')) LIKE '%NIKE%'
                        OR upper(coalesce(name, '')) ~ '(^|[^A-Z0-9])NI([^A-Z0-9]|$)'
                        OR coalesce(name, '') LIKE '%耐克%'
                        OR coalesce(name, '') LIKE '%千百度女鞋%'
                   )
                """
            ),
            {"default_brand": CBANNER_MENS_BRAND},
        )
        connection.execute(text("ALTER TABLE IF EXISTS suppliers ALTER COLUMN brand SET NOT NULL"))
        connection.execute(text("DROP INDEX IF EXISTS idx_suppliers_brand"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_suppliers_brand ON suppliers (brand)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_suppliers_factory_grade ON suppliers (factory_grade)"))
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
    def _filter_table_payload(table, data: Mapping[str, object]) -> dict[str, object]:
        allowed = set(table.c.keys())
        return {
            key: value
            for key, value in data.items()
            if key in allowed
        }

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        normalized = value.normalize()
        return str(normalized) if normalized.as_tuple().exponent < 0 else str(int(normalized))

    @staticmethod
    def _clear_accounting_record_summary(record: dict[str, object]) -> dict[str, object]:
        if record.get("document_type") in ACCOUNTING_DOCUMENT_TYPES:
            record["total_count"] = None
            record["amount"] = None
            record["warehouse"] = None
        return record

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
        if payload.get("document_type") in ACCOUNTING_DOCUMENT_TYPES:
            payload["total_count"] = None
            payload["amount"] = None
            payload["warehouse"] = None
        raw_payload = payload.get("raw_payload")
        if isinstance(raw_payload, Mapping):
            payload["raw_payload"] = {
                k: str(v) if isinstance(v, Decimal) else v
                for k, v in raw_payload.items()
            }
        return payload

    @staticmethod
    def _document_number_prefix(document_type: object) -> str:
        return DOCUMENT_NUMBER_PREFIXES.get(str(document_type or "").strip(), DEFAULT_DOCUMENT_NUMBER_PREFIX)

    @staticmethod
    def _document_number_date_text(date_value: object) -> str:
        parsed_date = date_value if isinstance(date_value, date) else parse_date(date_value)
        return (parsed_date or date.today()).strftime("%Y-%m-%d")

    @staticmethod
    def _format_document_number(document_type: object, date_value: object, sequence: int) -> str:
        prefix = InventoryRepository._document_number_prefix(document_type)
        date_text = InventoryRepository._document_number_date_text(date_value)
        return f"{prefix}-{date_text}-{sequence:04d}"

    @staticmethod
    def _generate_document_number(connection, date_value: object, document_type: object) -> str:
        prefix = InventoryRepository._document_number_prefix(document_type)
        date_text = InventoryRepository._document_number_date_text(date_value)
        pattern = f"{prefix}-{date_text}-%"
        rows = connection.execute(
            select(INVENTORY_TABLE.c.document_number)
            .where(INVENTORY_TABLE.c.document_number.like(pattern))
        ).all()
        max_sequence = 0
        for row in rows:
            suffix = str(row[0] or "").rsplit("-", 1)[-1]
            if suffix.isdigit():
                max_sequence = max(max_sequence, int(suffix))
        return f"{prefix}-{date_text}-{max_sequence + 1:04d}"

    @staticmethod
    def _backfill_document_numbers(connection) -> None:
        rows = list(connection.execute(
            select(
                INVENTORY_TABLE.c.id,
                INVENTORY_TABLE.c.date,
                INVENTORY_TABLE.c.date_value,
                INVENTORY_TABLE.c.document_type,
                INVENTORY_TABLE.c.document_number,
            )
            .order_by(
                INVENTORY_TABLE.c.date_value.nulls_last(),
                INVENTORY_TABLE.c.date,
                INVENTORY_TABLE.c.document_type,
                INVENTORY_TABLE.c.id,
            )
        ).mappings())
        counters: dict[tuple[str, str], int] = {}
        for row in rows:
            date_value = row.get("date_value") or row.get("date")
            document_type = row.get("document_type")
            prefix = InventoryRepository._document_number_prefix(document_type)
            date_text = InventoryRepository._document_number_date_text(date_value)
            key = (prefix, date_text)
            counters[key] = counters.get(key, 0) + 1
            document_number = InventoryRepository._format_document_number(document_type, date_value, counters[key])
            if row.get("document_number") == document_number:
                continue
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
            "wechat": str(data.get("wechat") or "").strip() or None,
            "cooperation_status": str(data.get("cooperation_status") or "").strip() or None,
            "address": str(data.get("address") or "").strip() or None,
            "notes": str(data.get("notes") or "").strip() or None,
        }
        if "factory_grade" in data:
            payload["factory_grade"] = str(data.get("factory_grade") or "").strip() or None
        if "factory_suggestion" in data:
            payload["factory_suggestion"] = str(data.get("factory_suggestion") or "").strip() or None
        if payload["brand"] not in SUPPLIER_BRANDS:
            payload["brand"] = CBANNER_MENS_BRAND
        return payload
