from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from itertools import groupby
from threading import Lock
from uuid import uuid4

from pathlib import Path

import orjson
from openpyxl import load_workbook
from psycopg import Error as PsycopgError, sql
from psycopg.types.json import Json
from sqlalchemy import JSON, MetaData, Table, Text, and_, case, cast, create_engine, delete, desc, func, insert, inspect, literal, or_, select, text, true, tuple_, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError

from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.inventory_schema import GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE, GENERAL_CUSTOMER_UNIT_TABLE, INVENTORY_ACCOUNT_SUBJECT_TABLE, INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, JST_STOCK_TABLE, PURCHASE_ORDER_REQUIREMENT_TABLE, PURCHASE_PRINT_TEMPLATE_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE, WAREHOUSE_BRAND_TABLE, WAREHOUSE_TABLE
from domain.inventory_sources import ACCOUNTING_DOCUMENT_TYPES, ACCOUNT_SUBJECT_CATEGORIES
from domain.inventory_template_import import validate_template_document_numbers
from domain.inventory_brands import inventory_brand_filter_aliases, inventory_brand_options
from domain.gj_brand import CBANNER_MENS_BRAND, EBLAN_BRAND, EBLAN_WOMENS_SUPPLIER_BRAND, GJ_FINE_TABLE_BRANDS, SUPPLIER_BRANDS, infer_supplier_brand_from_name
from domain import jst_stock_snapshot_schema  # noqa: F401 - register JST stock snapshot tables on METADATA
from domain import product_goods_schema  # noqa: F401 - register goods table overrides on METADATA
from domain import product_size_group_mapping_schema  # noqa: F401 - register product size group mappings on METADATA
from domain import data_governance_schema  # noqa: F401 - register data-governance tables on METADATA
from domain import size_group_schema  # noqa: F401 - register size group tables on METADATA
from domain.jst_stock_snapshot_schema import JST_SIZE_STOCK_SNAPSHOT_TABLE, JST_STOCK_SUMMARY_SNAPSHOT_TABLE
from domain.product_goods_schema import PRODUCT_GOODS_OVERRIDES_TABLE
from domain.product_goods_historical_sales_schema import HISTORICAL_SALES_YEARS, ensure_product_goods_historical_sales_table
from domain.product_size_group_mapping_schema import PRODUCT_SIZE_GROUP_MAPPINGS_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE, ensure_product_archive_identity_schema
from domain.product_archive_naming import manual_product_table_name
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.size_group_schema import SIZE_GROUP_ITEMS_TABLE, SIZE_GROUPS_TABLE
from storage.date_normalization import parse_date, parse_month_day
from storage.schema_compat import ensure_columns, ensure_not_null
from storage.product_archive_table_names import allocate_product_table_name
from storage.detail_selection import selected_detail_values
from storage.inventory_import_tasks import complete_inventory_import
from storage.warehouse_inventory_cache import MAX_GROUPS, MAX_BARCODE_GROUPS, CompressedInventoryGroups, InventoryGroups, WarehouseInventoryCache
from domain.warehouse_inventory_revision_schema import CAPABILITIES_SQL, VERSION_SQL
from domain.inventory_import_task_schema import INVENTORY_IMPORT_TASK_TABLE


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
SUPPLIER_LEDGER_INCREASE_TYPES = ("进货单", "应付款增加")
SUPPLIER_LEDGER_DECREASE_TYPES = ("进货退货单", "应付款减少")
SUPPLIER_LEDGER_NEUTRAL_TYPES = ("同价调拨单",)
CUSTOMER_LEDGER_INCREASE_TYPES = ("批发销售单", "应收款增加")
CUSTOMER_LEDGER_DECREASE_TYPES = ("批发销售退货单", "应收款减少")
WHOLESALE_DOCUMENT_TYPES = ("批发销售单", "批发销售退货单")
NON_SUPPLIER_COUNTERPARTY_TYPES = (
    *CUSTOMER_LEDGER_INCREASE_TYPES,
    *CUSTOMER_LEDGER_DECREASE_TYPES,
    *SUPPLIER_LEDGER_NEUTRAL_TYPES,
)
NEGATIVE_TOTAL_DOCUMENT_TYPES = {"进货退货单"}
PURCHASE_INBOUND_DETAIL_TYPES = ("进货单", "进货退货单")
WAREHOUSE_INBOUND_TYPES = ("进货单", "报溢单", "批发销售退货单")
WAREHOUSE_OUTBOUND_TYPES = ("进货退货单", "报损单", "批发销售单")
GENERAL_CUSTOMER_SORT_SCOPE_BRAND = "brand"
GENERAL_CUSTOMER_SORT_SCOPE_SHOP = "shop"
GENERAL_CUSTOMER_SORT_SCOPE_UNIT = "unit"

GENERAL_CUSTOMER_ROOT_SORT_PARENT_ID = 0
TEMPLATE_DETAIL_WRITE_BATCH_SIZE = 5000
TEMPLATE_DETAIL_COPY_MIN_ROWS = 100
TEMPLATE_TOTALS_BATCH_SIZE = 1000
SUMMARY_SEARCH_WHITESPACE = " \t\r\n\v\f\u00a0\u3000"

# Parse and validate concurrently, but wait for the local writer before opening
# a transaction. The PostgreSQL advisory lock below still protects other processes.
_INVENTORY_IMPORT_WRITE_LOCK = Lock()


def _json_serializer(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


class InventoryRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )
        self._product_identity_schema_ready = False
        self._warehouse_inventory_cache = WarehouseInventoryCache()
        self.create_tables()

    # ── Inventory Records ──────────────────────────────────────────

    def list_records(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
        supplier: str | None = None,
        suppliers: list[str] | None = None,
        brands: list[str] | None = None,
        warehouse: str | None = None,
        warehouses: list[str] | None = None,
        document_type: str | None = None,
        document_types: list[str] | None = None,
        exclude_document_type: str | None = None,
        document_number: str | None = None,
        summary: str | None = None,
        original_sku: str | None = None,
        product_code: str | None = None,
        handler: str | None = None,
        completion_status: str | None = None,
        sort_by: str | None = None,
        sort_direction: str = "desc",
        sort_rules: list[tuple[str, str]] | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        table = INVENTORY_TABLE
        totals_statement = select(
            func.count().label("record_count"),
            func.coalesce(
                func.sum(case(
                    (table.c.document_type == "进货退货单", func.abs(func.coalesce(table.c.total_count, 0))),
                    else_=func.coalesce(table.c.total_count, 0),
                )),
                0,
            ).label("total_count"),
            func.coalesce(
                func.sum(case(
                    (table.c.document_type == "进货退货单", func.abs(func.coalesce(table.c.amount, 0))),
                    else_=func.coalesce(table.c.amount, 0),
                )),
                0,
            ).label("amount"),
        ).select_from(table)
        items_statement = select(table)

        conditions = self._record_filter_conditions(
            date_start=date_start,
            date_end=date_end,
            supplier=supplier,
            suppliers=suppliers,
            brands=brands,
            warehouse=warehouse,
            warehouses=warehouses,
            document_type=document_type,
            document_types=document_types,
            exclude_document_type=exclude_document_type,
            document_number=document_number,
            summary=summary,
            original_sku=original_sku,
            product_code=product_code,
            handler=handler,
            completion_status=completion_status,
        )
        if conditions:
            criterion = conditions[0] if len(conditions) == 1 else and_(*conditions)
            items_statement = items_statement.where(criterion)
            totals_statement = totals_statement.where(criterion)

        sort_columns = {
            "document_number": table.c.document_number,
            "date": table.c.date_value,
            "delivery_date": table.c.extra_fields["delivery_date"].as_string(),
            "document_type": table.c.document_type,
            "supplier": case((table.c.document_type == "同价调拨单", None), else_=table.c.supplier),
            "total_count": table.c.total_count,
            "amount": table.c.amount,
            "warehouse": table.c.warehouse,
            "outbound_warehouse": case((table.c.document_type == "同价调拨单", table.c.supplier), else_=None),
            "handler": table.c.handler,
            "summary": table.c.summary,
            "additional_note": table.c.additional_note,
            "updated_at": table.c.updated_at,
        }
        normalized_sort_rules = list(sort_rules or [])
        if not normalized_sort_rules and sort_by:
            normalized_sort_rules = [(str(sort_by).strip(), str(sort_direction or "desc").lower())]
        order_by = []
        sort_expressions = []
        seen_sort_keys: set[str] = set()
        for sort_key, direction in normalized_sort_rules:
            normalized_key = str(sort_key or "").strip()
            sort_column = sort_columns.get(normalized_key)
            if sort_column is None or normalized_key in seen_sort_keys:
                continue
            seen_sort_keys.add(normalized_key)
            sort_expressions.append((sort_column, str(direction or "").lower() == "asc"))
            if str(direction or "").lower() == "asc":
                order_by.append(sort_column.asc().nulls_last())
            else:
                order_by.append(sort_column.desc().nulls_last())
        if not order_by:
            order_by = [desc(table.c.id)]
        else:
            order_by.append(desc(table.c.id))
        items_statement = items_statement.order_by(*order_by).offset((page - 1) * page_size).limit(page_size)

        with self.engine.connect() as connection:
            # Selective searches and incomplete documents often need to inspect
            # every candidate even for the first page. Share that work between
            # totals and pagination, materializing only IDs and numeric/sort data.
            share_matches = bool(
                product_code or original_sku
                or (summary or "").translate(str.maketrans("", "", SUMMARY_SEARCH_WHITESPACE)).strip()
                or completion_status == "incomplete"
            )
            if share_matches:
                matches = select(
                    table.c.id.label("record_id"), table.c.document_type,
                    table.c.total_count, table.c.amount,
                    *(column.label(f"sort_{index}") for index, (column, _) in enumerate(sort_expressions)),
                ).where(*conditions).cte("inventory_record_matches")
                if connection.dialect.name == "postgresql":
                    matches = matches.prefix_with("MATERIALIZED")
                matched_order = [
                    (matches.c[f"sort_{index}"].asc() if ascending else matches.c[f"sort_{index}"].desc()).nulls_last()
                    for index, (_, ascending) in enumerate(sort_expressions)
                ] + [matches.c.record_id.desc()]
                page_matches = (
                    select(matches).order_by(*matched_order)
                    .offset((page - 1) * page_size).limit(page_size).cte("inventory_record_page")
                )
                matched_totals = select(
                    func.count().label("record_count"),
                    func.coalesce(func.sum(case(
                        (matches.c.document_type == "进货退货单", func.abs(func.coalesce(matches.c.total_count, 0))),
                        else_=func.coalesce(matches.c.total_count, 0),
                    )), 0).label("quantity_total"),
                    func.coalesce(func.sum(case(
                        (matches.c.document_type == "进货退货单", func.abs(func.coalesce(matches.c.amount, 0))),
                        else_=func.coalesce(matches.c.amount, 0),
                    )), 0).label("amount_total"),
                ).select_from(matches).subquery("inventory_record_totals")
                page_order = [
                    (page_matches.c[f"sort_{index}"].asc() if ascending else page_matches.c[f"sort_{index}"].desc()).nulls_last()
                    for index, (_, ascending) in enumerate(sort_expressions)
                ] + [page_matches.c.record_id.desc()]
                statement = select(
                    table, matched_totals.c.record_count,
                    matched_totals.c.quantity_total, matched_totals.c.amount_total,
                ).select_from(
                    matched_totals.outerjoin(page_matches, true())
                    .outerjoin(table, table.c.id == page_matches.c.record_id)
                ).order_by(*page_order)
                rows = connection.execute(statement).mappings().all()
                total = int(rows[0]["record_count"])
                all_totals = {"total_count": rows[0]["quantity_total"], "amount": rows[0]["amount_total"]}
                items = [{column.name: row[column.name] for column in table.c} for row in rows if row["id"] is not None]
            else:
                all_totals = connection.execute(totals_statement).mappings().one()
                total = int(all_totals["record_count"])
                items = [dict(row) for row in connection.execute(items_statement).mappings()] if (page - 1) * page_size < total else []
        for item in items:
            self._clear_accounting_record_summary(item)
            if item.get("document_type") == "进货退货单":
                for field in ("total_count", "amount"):
                    if item.get(field) is not None:
                        item[field] = abs(Decimal(str(item[field])))

        page_total_count = sum(
            (Decimal(str(item.get("total_count") or "0")) for item in items),
            Decimal("0"),
        )
        page_amount = sum(
            (Decimal(str(item.get("amount") or "0")) for item in items),
            Decimal("0"),
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "totals": {
                "current_page": {
                    "total_count": self._format_decimal(page_total_count),
                    "amount": self._format_decimal(page_amount),
                },
                "all": {
                    "total_count": self._format_decimal(Decimal(str(all_totals["total_count"] or "0"))),
                    "amount": self._format_decimal(Decimal(str(all_totals["amount"] or "0"))),
                },
            },
        }

    @staticmethod
    def _record_completion_condition(completion_status: str):
        """Share the ledger's completion rules with warehouse stock queries."""
        table = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE.alias("completion_detail")
        internal_customer_names = union_all(
            select(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name)
            .where(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name.ilike("%内销客户%")),
            select(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name)
            .join(GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
            .where(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name.ilike("%内销客户%")),
        )
        always_completed = or_(
            func.coalesce(table.c.supplier.in_(internal_customer_names), False),
            and_(
                table.c.document_type.is_not(None),
                table.c.document_type.in_(WHOLESALE_DOCUMENT_TYPES),
                func.replace(func.coalesce(table.c.supplier, ""), " ", "").like("%总部采购%"),
            ),
        )
        # Correlate only to the document, even when the outer query joins details.
        detail_query = select(detail.c.id).where(detail.c.document_id == table.c.id).correlate(table)
        has_details = detail_query.exists()
        has_missing_amount = detail_query.where(or_(detail.c.amount.is_(None), detail.c.amount == 0)).exists()
        has_missing_price = detail_query.where(or_(detail.c.unit_price.is_(None), detail.c.unit_price == 0)).exists()
        is_accounting_document = table.c.document_type.in_(ACCOUNTING_DOCUMENT_TYPES)
        is_product_document = or_(table.c.document_type.is_(None), ~is_accounting_document)
        if completion_status == "incomplete":
            return and_(
                ~always_completed,
                or_(
                    ~has_details,
                    and_(is_accounting_document, has_missing_amount),
                    and_(is_product_document, has_missing_price),
                ),
            )
        return or_(
            always_completed,
            and_(
                has_details,
                or_(
                    and_(is_accounting_document, ~has_missing_amount),
                    and_(is_product_document, ~has_missing_price),
                ),
            ),
        )

    def _record_filter_conditions(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
        supplier: str | None = None,
        suppliers: list[str] | None = None,
        brands: list[str] | None = None,
        warehouse: str | None = None,
        warehouses: list[str] | None = None,
        document_type: str | None = None,
        document_types: list[str] | None = None,
        exclude_document_type: str | None = None,
        document_number: str | None = None,
        summary: str | None = None,
        original_sku: str | None = None,
        product_code: str | None = None,
        handler: str | None = None,
        completion_status: str | None = None,
    ):
        table = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        stock = JST_STOCK_TABLE
        conditions = [table.c.deleted_at.is_(None)]
        if date_start:
            parsed = parse_date(date_start)
            conditions.append(table.c.date_value >= parsed if parsed else table.c.date >= date_start)
        if date_end:
            parsed = parse_date(date_end)
            conditions.append(table.c.date_value <= parsed if parsed else table.c.date <= date_end)
        supplier_values = [str(value).strip() for value in (suppliers or []) if str(value).strip()]
        if supplier_values:
            conditions.append(table.c.supplier.in_(supplier_values))
        elif supplier:
            conditions.append(table.c.supplier.ilike(f"%{supplier.strip()}%"))
        warehouse_values = [str(value).strip() for value in (warehouses or []) if str(value).strip()]
        if warehouse_values:
            conditions.append(or_(
                table.c.warehouse.in_(warehouse_values),
                and_(table.c.document_type == "同价调拨单", table.c.supplier.in_(warehouse_values)),
            ))
        elif warehouse:
            conditions.append(or_(
                table.c.warehouse == warehouse,
                and_(table.c.document_type == "同价调拨单", table.c.supplier == warehouse),
            ))
        document_type_values = [str(value).strip() for value in (document_types or []) if str(value).strip()]
        if document_type_values:
            conditions.append(table.c.document_type.in_(document_type_values))
        elif document_type:
            conditions.append(table.c.document_type == document_type)
        brand_values = [str(value).strip() for value in (brands or []) if str(value).strip()]
        if brand_values:
            with self.engine.connect() as connection:
                supplier_brands = connection.execute(
                    select(SUPPLIER_BRAND_TABLE.c.code, SUPPLIER_BRAND_TABLE.c.name)
                ).mappings().all()
            aliases = inventory_brand_filter_aliases(brand_values, supplier_brands)
            warehouse_names = select(func.trim(WAREHOUSE_TABLE.c.name)).where(
                func.lower(func.trim(WAREHOUSE_TABLE.c.brand)).in_(aliases)
            )
            supplier_names = select(func.trim(SUPPLIER_TABLE.c.name)).where(
                func.lower(func.trim(SUPPLIER_TABLE.c.brand)).in_(aliases)
            )
            shop_names = select(func.trim(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name)).where(
                func.lower(func.trim(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name)).in_(aliases)
            )
            unit_names = (
                select(func.trim(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name))
                .join(GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
                .where(func.lower(func.trim(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name)).in_(aliases))
            )
            conditions.append(or_(
                func.trim(table.c.warehouse).in_(warehouse_names),
                func.trim(table.c.supplier).in_(supplier_names),
                func.trim(table.c.supplier).in_(shop_names),
                func.trim(table.c.supplier).in_(unit_names),
                and_(table.c.document_type == "同价调拨单", func.trim(table.c.supplier).in_(warehouse_names)),
            ))
        if exclude_document_type:
            conditions.append(or_(table.c.document_type.is_(None), table.c.document_type != exclude_document_type))
        if document_number and document_number.strip():
            conditions.append(table.c.document_number.ilike(f"%{document_number.strip()}%"))
        normalized_summary = (summary or "").translate(str.maketrans("", "", SUMMARY_SEARCH_WHITESPACE)).strip()
        if normalized_summary:
            summary_column = table.c.summary
            for whitespace in SUMMARY_SEARCH_WHITESPACE:
                summary_column = func.replace(summary_column, whitespace, "")
            conditions.append(summary_column.ilike(f"%{normalized_summary}%"))
        handler_values = list(dict.fromkeys(
            value.strip() for value in re.split(r"[,，;；、\r\n]+", handler or "") if value.strip()
        ))
        if handler_values:
            conditions.append(or_(*(table.c.handler.ilike(f"%{value}%") for value in handler_values)))
        if completion_status in ("completed", "incomplete"):
            conditions.append(self._record_completion_condition(completion_status))
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
            # Read matching snapshot codes once, even when the same SKU occurs
            # on many stock dates. PostgreSQL materializes this shared CTE.
            matching_stock_codes = (
                select(stock.c.product_code)
                .where(stock.c.product_code.ilike(product_like))
                .distinct()
                .cte("inventory_matching_stock_codes")
            )
            stock_code = matching_stock_codes.c.product_code
            stock_candidates = union_all(
                select(stock_code.label("candidate")),
                select(func.left(stock_code, func.length(stock_code) - 5).label("candidate"))
                .where(func.length(stock_code) > 5),
                select(func.left(stock_code, func.length(stock_code) - 3).label("candidate"))
                .where(func.length(stock_code) > 3),
                select(func.left(stock_code, func.length(stock_code) - 2).label("candidate"))
                .where(func.length(stock_code) > 2),
            ).subquery()
            candidates = (
                select(stock_candidates.c.candidate)
                .where(stock_candidates.c.candidate.is_not(None))
                .where(stock_candidates.c.candidate != "")
                .distinct()
                .subquery()
            )
            # Keep substring and exact-code matches in separate indexable
            # branches. An OR with the stock subquery forced a full detail scan.
            matching_documents = union_all(
                select(detail.c.document_id).where(detail.c.product_code.ilike(product_like)),
                select(detail.c.document_id).select_from(
                    candidates.join(detail, detail.c.product_code == candidates.c.candidate)
                ),
            )
            conditions.append(table.c.id.in_(matching_documents))

        return conditions

    def list_record_ids(self, **filters) -> list[int]:
        conditions = self._record_filter_conditions(**filters)
        with self.engine.connect() as connection:
            return list(connection.execute(
                select(INVENTORY_TABLE.c.id).where(*conditions).order_by(INVENTORY_TABLE.c.id)
            ).scalars())

    def list_purchase_inbound_details(self, **filters) -> dict[str, object]:
        return self._list_purchase_product_details(document_types=PURCHASE_INBOUND_DETAIL_TYPES, **filters)

    def list_purchase_order_details(self, **filters) -> dict[str, object]:
        """Flatten active purchase orders without applying receipt completion rules."""
        return self._list_purchase_product_details(document_types=("进货订单",), **filters)

    def list_sales_details(self, **filters) -> dict[str, object]:
        return self._list_purchase_product_details(
            document_types=WHOLESALE_DOCUMENT_TYPES,
            quantity_field="sales_quantity", amount_field="sales_amount", **filters,
        )

    def _list_purchase_product_details(
        self,
        *,
        document_types: tuple[str, ...],
        quantity_field: str = "purchase_quantity",
        amount_field: str = "purchase_amount",
        date_start: str | None = None,
        date_end: str | None = None,
        brands: list[str] | None = None,
        document_type: str | None = None,
        supplier: str | None = None,
        warehouse: list[str] | None = None,
        product_code: str | None = None,
        product_name: str | None = None,
        color_name: str | None = None,
        size_name: str | None = None,
        sort_direction: str = "asc",
        display_mode: str = "goods",
        selected_rows: list[str] | None = None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        if sort_direction not in {"asc", "desc"}:
            raise ValueError("日期排序仅支持 asc 或 desc")
        if display_mode not in {"goods", "barcode"}:
            raise ValueError("明细展示仅支持按货号或按编码")

        def date_order(columns, detail_id):
            # Use the same stable order before LIMIT and after joining display
            # fields, so equal dates cannot move between pages.
            date_value = columns.date_value.desc() if sort_direction == "desc" else columns.date_value.asc()
            legacy_date = columns.date.desc() if sort_direction == "desc" else columns.date.asc()
            return date_value.nulls_last(), legacy_date.nulls_last(), columns.document_number, detail_id

        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        joined = detail.join(record, detail.c.document_id == record.c.id)
        warehouse_values = [warehouse] if isinstance(warehouse, str) else (warehouse or [])
        warehouse_names = list(dict.fromkeys(
            warehouse_name.strip()
            for warehouse_name in warehouse_values
            if warehouse_name and warehouse_name.strip()
        ))
        conditions = self._record_filter_conditions(
            date_start=date_start,
            date_end=date_end,
            brands=brands,
            document_types=list(document_types),
            supplier=supplier,
            warehouses=warehouse_names,
        )
        if document_type:
            conditions.append(record.c.document_type == document_type)
        if product_code:
            conditions.append(detail.c.product_code.ilike(f"%{product_code.strip()}%"))
        if product_name:
            conditions.append(detail.c.product_name.ilike(f"%{product_name.strip()}%"))
        if color_name:
            color_like = f"%{color_name.strip()}%"
            conditions.append(or_(detail.c.color_name.ilike(color_like), detail.c.color_spec.ilike(color_like)))
        if size_name and display_mode == "goods":
            conditions.append(detail.c.size_quantities.cast(Text).ilike(f"%\"{size_name.strip()}\"%"))
        if selected_rows is not None:
            conditions.append(detail.c.id.in_(selected_detail_values(selected_rows, self.engine.dialect.name, ids=True)))

        criterion = and_(*conditions)
        is_sales = document_types == WHOLESALE_DOCUMENT_TYPES
        return_type = "批发销售退货单" if is_sales else "进货退货单"
        return_quantity = func.coalesce(detail.c.quantity, 0)
        return_amount = func.coalesce(detail.c.amount, 0)
        if is_sales:
            # Imported returns may already be negative; deduct them once.
            return_quantity = func.abs(return_quantity)
            return_amount = func.abs(return_amount)
        signed_quantity = case(
            (record.c.document_type == return_type, -return_quantity),
            else_=func.coalesce(detail.c.quantity, 0),
        )
        signed_amount = case(
            (record.c.document_type == return_type, -return_amount),
            else_=func.coalesce(detail.c.amount, 0),
        )
        if display_mode == "barcode":
            from storage.inventory_detail_barcodes import list_detail_barcodes
            return list_detail_barcodes(
                self, criterion=criterion, signed_quantity=signed_quantity, signed_amount=signed_amount,
                return_type=return_type, is_sales=is_sales, sort_direction=sort_direction,
                page=page, page_size=page_size, size_name=size_name,
                quantity_field=quantity_field, amount_field=amount_field,
                selected_rows=selected_rows,
            )
        share_matches = document_types == ("进货订单",)
        if share_matches:
            # Reuse the filtered purchase rows for totals and pagination. The
            # materialization also prevents a LIMIT-driven date index scan over
            # unrelated document types. Keep JSON and display fields out of it.
            matches = select(
                detail.c.id.label("detail_id"),
                record.c.date_value, record.c.date, record.c.document_number,
                signed_quantity.label("quantity"), signed_amount.label("amount"),
            ).select_from(joined).where(criterion).cte("purchase_order_detail_matches")
            if self.engine.dialect.name == "postgresql":
                matches = matches.prefix_with("MATERIALIZED")
            totals_statement = select(
                func.count().label("detail_count"),
                func.coalesce(func.sum(matches.c.quantity), 0).label("quantity_total"),
                func.coalesce(func.sum(matches.c.amount), 0).label("purchase_amount_total"),
            ).select_from(matches)
            page_statement = select(
                matches.c.detail_id, matches.c.date_value, matches.c.date, matches.c.document_number,
            ).order_by(*date_order(matches.c, matches.c.detail_id))
        else:
            totals_statement = select(
                func.count().label("detail_count"),
                func.coalesce(func.sum(signed_quantity), 0).label("quantity_total"),
                func.coalesce(func.sum(signed_amount), 0).label("purchase_amount_total"),
            ).select_from(joined).where(criterion)
            page_statement = select(
                detail.c.id.label("detail_id"), record.c.date_value, record.c.date, record.c.document_number,
            ).select_from(joined).where(criterion).order_by(
                *date_order(record.c, detail.c.id),
            )
        page_details = (
            page_statement
            .offset((page - 1) * page_size)
            .limit(page_size)
            .cte("purchase_order_detail_page" if share_matches else "purchase_inbound_page")
        )
        page_source = page_details.join(detail, detail.c.id == page_details.c.detail_id).join(
            record, record.c.id == detail.c.document_id,
        )
        total_columns = []
        if share_matches:
            matched_totals = totals_statement.subquery("purchase_order_detail_totals")
            # An outer join keeps all totals even for empty or out-of-range pages.
            page_source = matched_totals.outerjoin(page_details, true()).outerjoin(
                detail, detail.c.id == page_details.c.detail_id,
            ).outerjoin(record, record.c.id == detail.c.document_id)
            total_columns = list(matched_totals.c)
        items_statement = (
            select(
                detail.c.id,
                detail.c.document_id,
                detail.c.product_code,
                detail.c.product_name,
                detail.c.color_name,
                detail.c.color_spec,
                detail.c.size_quantities,
                detail.c.quantity,
                detail.c.unit_price,
                detail.c.amount,
                detail.c.extra_fields,
                record.c.document_type,
                record.c.document_number,
                record.c.date,
                record.c.supplier,
                record.c.warehouse,
                *total_columns,
            )
            .select_from(page_source)
            .order_by(*date_order(page_details.c, page_details.c.detail_id))
        )

        with self.engine.connect() as connection:
            if share_matches:
                matched_rows = connection.execute(items_statement).mappings().all()
                totals = matched_rows[0]
                total = int(totals["detail_count"])
                rows = [dict(row) for row in matched_rows if row["id"] is not None]
            else:
                totals = connection.execute(totals_statement).mappings().one()
                total = int(totals["detail_count"])
                rows = (
                    [dict(row) for row in connection.execute(items_statement).mappings()]
                    if (page - 1) * page_size < total else []
                )
            supplier_names = sorted({
                str(row.get("supplier") or "").strip()
                for row in rows
                if str(row.get("supplier") or "").strip()
            })
            supplier_codes: dict[str, str] = {}
            if supplier_names and not is_sales:
                supplier_rows = connection.execute(
                    select(SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.factory_code)
                    .where(SUPPLIER_TABLE.c.name.in_(supplier_names))
                ).mappings()
                for supplier_row in supplier_rows:
                    name = str(supplier_row.get("name") or "").strip()
                    if not name:
                        continue
                    code = str(supplier_row.get("factory_code") or "").strip()
                    if code or name not in supplier_codes:
                        supplier_codes[name] = code

        items: list[dict[str, object]] = []
        offset = (page - 1) * page_size
        for index, row in enumerate(rows, start=1):
            document_type_text = str(row.get("document_type") or "")
            quantity = Decimal(str(row.get("quantity") or "0"))
            purchase_amount = Decimal(str(row.get("amount") or "0"))
            if document_type_text == return_type:
                quantity = -abs(quantity) if is_sales else -quantity
                purchase_amount = -abs(purchase_amount) if is_sales else -purchase_amount
            extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
            supplier_name = str(row.get("supplier") or "").strip()
            items.append({
                "row_number": offset + index,
                "detail_id": row.get("id"),
                "document_id": row.get("document_id"),
                "product_code": row.get("product_code"),
                "product_name": row.get("product_name"),
                "document_type": row.get("document_type"),
                "document_number": row.get("document_number"),
                "date": row.get("date"),
                quantity_field: self._format_decimal(quantity),
                amount_field: self._format_decimal(purchase_amount),
                "unit_price": self._format_decimal(row["unit_price"]) if row.get("unit_price") is not None else None,
                "retail_amount": "",
                "factory_code": extra_fields.get("factory_code") or "",
                "unit_code": supplier_codes.get(supplier_name, ""),
                "unit_name": row.get("supplier"),
                "warehouse_name": row.get("warehouse"),
                "color_name": row.get("color_name") or row.get("color_spec") or "",
                "size_quantities": row.get("size_quantities") if isinstance(row.get("size_quantities"), dict) else {},
            })

        quantity_total = Decimal(str(totals.get("quantity_total") or "0"))
        purchase_amount_total = Decimal(str(totals.get("purchase_amount_total") or "0"))
        page_quantity_total = sum(
            (Decimal(str(item.get(quantity_field) or "0")) for item in items),
            Decimal("0"),
        )
        page_purchase_amount_total = sum(
            (Decimal(str(item.get(amount_field) or "0")) for item in items),
            Decimal("0"),
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "totals": {
                quantity_field: self._format_decimal(quantity_total),
                amount_field: self._format_decimal(purchase_amount_total),
                "retail_amount": "",
                "current_page": {
                    quantity_field: self._format_decimal(page_quantity_total),
                    amount_field: self._format_decimal(page_purchase_amount_total),
                    "retail_amount": "",
                },
                "all": {
                    quantity_field: self._format_decimal(quantity_total),
                    amount_field: self._format_decimal(purchase_amount_total),
                    "retail_amount": "",
                },
            },
        }

    def get_record(self, record_id: int) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        statement = select(table).where(table.c.id == record_id, table.c.deleted_at.is_(None))
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_record_any_status(self, record_id: int) -> dict[str, object] | None:
        table = INVENTORY_TABLE
        statement = select(table).where(table.c.id == record_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_record_for_append(
        self,
        *,
        date_value: object,
        warehouse: object,
        document_type: object,
        summary: object,
        supplier: object | None = None,
        allow_empty_warehouse: bool = False,
        match_warehouse: bool = True,
    ) -> dict[str, object] | None:
        normalized_summary = str(summary or "").strip()
        normalized_warehouse = str(warehouse or "").strip()
        normalized_document_type = str(document_type or "").strip()
        normalized_date = parse_date(date_value)
        if not (normalized_summary and normalized_document_type and normalized_date):
            return None
        if match_warehouse and not normalized_warehouse and not allow_empty_warehouse:
            return None

        table = INVENTORY_TABLE
        statement = (
            select(table)
            .where(
                table.c.deleted_at.is_(None),
                or_(
                    table.c.date_value == normalized_date,
                    table.c.date == normalized_date.isoformat(),
                ),
                table.c.document_type == normalized_document_type,
                table.c.summary == normalized_summary,
            )
            .order_by(desc(table.c.id))
        )
        if supplier is not None:
            normalized_supplier = str(supplier or "").strip()
            statement = statement.where(
                table.c.supplier == normalized_supplier if normalized_supplier else or_(table.c.supplier.is_(None), table.c.supplier == "")
            )
        if match_warehouse:
            statement = statement.where(
                table.c.warehouse == normalized_warehouse if normalized_warehouse else or_(table.c.warehouse.is_(None), table.c.warehouse == "")
            )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def purchase_import_targets(self, plans, *, connection=None, lock=False):
        """Find exact import targets in bounded batches without loading source JSON."""
        table = INVENTORY_TABLE
        keys = {
            (parse_date(plan["date"]), plan["document_type"], plan["supplier"] or "",
             plan["warehouse"] or "", plan["summary"])
            for plan in plans
        }
        if connection is None:
            with self.engine.connect() as connection:
                return self.purchase_import_targets(plans, connection=connection)
        found = {}
        batch_size = 100 if connection.dialect.name == "sqlite" else 500
        keys_list = list(keys)
        fields = (table.c.document_type, func.coalesce(table.c.supplier, ""),
                  func.coalesce(table.c.warehouse, ""), table.c.summary)
        for offset in range(0, len(keys_list), batch_size):
            batch = keys_list[offset:offset + batch_size]
            statement = select(
                table.c.id, table.c.document_number, table.c.date_value, table.c.date,
                table.c.document_type, table.c.supplier, table.c.warehouse, table.c.summary,
            ).where(
                table.c.deleted_at.is_(None),
                or_(table.c.date_value.in_({key[0] for key in batch}),
                    table.c.date.in_({key[0].isoformat() for key in batch})),
                table.c.document_type.in_({key[1] for key in batch}),
                or_(
                    tuple_(table.c.date_value, *fields).in_(batch),
                    tuple_(table.c.date, *fields).in_([(key[0].isoformat(), *key[1:]) for key in batch]),
                ),
            ).order_by(table.c.id.desc())
            if lock:
                statement = statement.with_for_update()
            batch_keys = set(batch)
            for row in connection.execute(statement).mappings():
                tail = (row["document_type"], row["supplier"] or "", row["warehouse"] or "", row["summary"])
                dates = {row["date_value"]}
                legacy_date = parse_date(row["date"])
                if legacy_date and row["date"] == legacy_date.isoformat():
                    dates.add(legacy_date)
                for date_value in dates:
                    key = (date_value, *tail)
                    if key in batch_keys:
                        found.setdefault(key, dict(row))
        return {str(plan["key"]): found.get((
            parse_date(plan["date"]), plan["document_type"], plan["supplier"] or "",
            plan["warehouse"] or "", plan["summary"],
        )) for plan in plans}

    def import_purchase_documents(self, plans, *, skipped=0, task_id):
        """Commit all purchase headers, batched details and task success together."""
        for plan in plans:
            validate_template_document_numbers(plan["details"], f"采购单（摘要：{plan['summary']}）")
            if not plan["details"]:
                raise ValueError(f"摘要 {plan['summary']}：没有可导入的明细")
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        created = replaced = detail_count = 0
        records = []
        with _INVENTORY_IMPORT_WRITE_LOCK, self.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL lock_timeout = '30s'"))
                connection.execute(text("SET LOCAL statement_timeout = '10min'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(42917001)"))
            supplier_names = {plan["supplier"] for plan in plans}
            if supplier_names:
                known = set()
                names = sorted(supplier_names)
                for offset in range(0, len(names), 5000):
                    known.update(connection.execute(select(SUPPLIER_TABLE.c.name).where(
                        SUPPLIER_TABLE.c.name.in_(names[offset:offset + 5000]),
                    )).scalars())
                if unknown := supplier_names - known:
                    raise ValueError(f"供应商档案已变化：{'、'.join(sorted(unknown))}，请重新预检查；本批次未提交")
            targets = self.purchase_import_targets(plans, connection=connection, lock=True)
            sequences = {}
            pending = []
            ids = []
            seen = set()
            for plan in plans:
                key = (plan["date"], plan["supplier"], plan["warehouse"], plan["summary"])
                target = targets[str(plan["key"])]
                expected = plan.get("existing_record")
                overwrite_changed = plan["decision"] == "overwrite" and (
                    not target or not expected or target["id"] != expected["id"]
                    or parse_date(target.get("date_value") or target.get("date")) != parse_date(plan["date"])
                )
                if key in seen or overwrite_changed or (plan["decision"] != "overwrite" and target):
                    raise ValueError(f"摘要 {plan['summary']} 的冲突或覆盖目标已变化，请重新预检查；本批次未提交")
                seen.add(key)
                payload = self._prepare_record(plan["record"])
                if target:
                    payload.pop("document_number", None)
                    document_id = target["id"]
                    connection.execute(delete(detail).where(detail.c.document_id == document_id))
                    connection.execute(update(record).where(record.c.id == document_id).values(**payload))
                    replaced += 1
                else:
                    payload["document_number"] = self._generate_document_number(
                        connection, plan["date"], "进货订单", sequences=sequences,
                    )
                    document_id = connection.execute(insert(record).values(**payload).returning(record.c.id)).scalar_one()
                    created += 1
                records.append({"id": document_id, "document_number": target["document_number"] if target else payload["document_number"]})
                ids.append(document_id)
                for row in plan["details"]:
                    pending.append(self._filter_table_payload(detail, self._coerce_empty(dict(row, document_id=document_id))))
                    if len(pending) >= TEMPLATE_DETAIL_WRITE_BATCH_SIZE:
                        self._insert_template_details(connection, pending)
                        pending.clear()
                detail_count += len(plan["details"])
            if pending:
                self._insert_template_details(connection, pending)
            self._update_template_totals(connection, ids, coalesce_empty=True)
            result = {"created": created, "replaced": replaced, "skipped": skipped, "details": detail_count}
            complete_inventory_import(connection, task_id, result)
        return {**result, "records": records}

    def get_records_by_date_summary(self, *, date_value: object, summary: object) -> list[dict[str, object]]:
        normalized_date = parse_date(date_value)
        normalized_summary = str(summary or "").strip()
        if not normalized_date or not normalized_summary:
            return []
        table = INVENTORY_TABLE
        statement = (
            select(table)
            .where(
                table.c.deleted_at.is_(None),
                or_(table.c.date_value == normalized_date, table.c.date == normalized_date.isoformat()),
                table.c.summary == normalized_summary,
            )
            .order_by(desc(table.c.id))
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def preview_template_documents(self, documents: list[object]) -> dict[str, object]:
        if not documents:
            return {"total": 0, "conflicts": []}
        record = INVENTORY_TABLE
        # Keep the same five-field identity as the write-time conflict check.
        # A historical workbook must not load every record (and its raw JSON)
        # on the same dates or compare every imported row to the entire table.
        def identity(document):
            return (document.date, document.document_type, document.supplier, document.warehouse, document.summary)

        keys = list(dict.fromkeys(identity(document) for document in documents))
        existing_numbers: dict[tuple[str, ...], str] = {}
        effective_date = case(
            (record.c.date_value.is_not(None), cast(record.c.date_value, Text)),
            else_=func.coalesce(record.c.date, ""),
        )
        match_columns = (
            effective_date, record.c.document_type, func.coalesce(record.c.supplier, ""),
            func.coalesce(record.c.warehouse, ""), record.c.summary,
        )
        batch_size = 500 if self.engine.dialect.name == "postgresql" else 100
        with self.engine.connect() as connection:
            for offset in range(0, len(keys), batch_size):
                batch = keys[offset:offset + batch_size]
                date_strings = {key[0] for key in batch}
                dates = {parse_date(value) for value in date_strings}
                statement = (
                    select(*match_columns, record.c.document_number)
                    .where(
                        record.c.deleted_at.is_(None),
                        or_(record.c.date_value.in_(dates), record.c.date.in_(date_strings)),
                        record.c.document_type.in_({key[1] for key in batch}),
                        record.c.supplier.in_({key[2] for key in batch})
                        if all(key[2] for key in batch) else true(),
                        tuple_(*match_columns).in_(batch),
                    )
                    .order_by(record.c.id.desc())
                )
                for row in connection.execute(statement).yield_per(500):
                    existing_numbers.setdefault(tuple(row[:5]), str(row[5] or ""))
        seen: set[tuple[str, ...]] = set()
        conflicts: list[dict[str, object]] = []
        for document in documents:
            key = identity(document)
            if key in existing_numbers or key in seen:
                conflicts.append({
                    "key": document.key, "date": document.date, "summary": document.summary,
                    "document_type": document.document_type,
                    "existing_number": existing_numbers.get(key, ""),
                    "can_merge": True,
                })
            seen.add(key)
        return {"total": len(documents), "conflicts": conflicts}

    def import_template_documents(self, plans: list[dict[str, object]], *, task_id: str | None = None) -> dict[str, int]:
        for plan in plans:
            if plan.get("decision") != "skip":
                label = f"{plan.get('date') or ''} {plan['document_type']}（摘要：{plan.get('summary') or ''}）"
                validate_template_document_numbers(plan.get("details") or [], label)
        record_table = INVENTORY_TABLE
        detail_table = INVENTORY_DETAIL_TABLE
        created = replaced = skipped = detail_count = 0
        with _INVENTORY_IMPORT_WRITE_LOCK, self.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                if task_id is not None:
                    connection.execute(text("SET LOCAL lock_timeout = '30s'"))
                    connection.execute(text("SET LOCAL statement_timeout = '10min'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(42917001)"))
            active_plans = [plan for plan in plans if plan.get("decision") != "skip"]
            supplier_names = {
                str(plan.get("supplier") or "").strip() for plan in active_plans
                if plan.get("document_type") in {"进货单", "进货退货单", "应付款增加", "应付款减少"}
            }
            customer_names = {
                str(plan.get("supplier") or "").strip() for plan in active_plans
                if plan.get("document_type") in {"批发销售单", "批发销售退货单", "应收款增加", "应收款减少"}
            }
            warehouse_names = {str(plan.get("warehouse") or "").strip() for plan in active_plans if plan.get("warehouse")}
            accounting_subjects = {
                str(detail.get("product_name") or "").strip()
                for plan in active_plans
                if plan.get("document_type") in ACCOUNTING_DOCUMENT_TYPES
                for detail in plan.get("details") or []
            }
            missing: list[str] = []
            if supplier_names:
                known = set(connection.execute(
                    select(SUPPLIER_TABLE.c.name).where(SUPPLIER_TABLE.c.name.in_(supplier_names))
                ).scalars())
                if unknown := supplier_names - known:
                    missing.append(f"供应商（供应商管理）：{'、'.join(sorted(unknown))}")
            if warehouse_names:
                known = set(connection.execute(
                    select(WAREHOUSE_TABLE.c.name).where(WAREHOUSE_TABLE.c.name.in_(warehouse_names))
                ).scalars())
                if unknown := warehouse_names - known:
                    missing.append(f"仓库（仓库管理）：{'、'.join(sorted(unknown))}")
            if customer_names:
                for name in customer_names:
                    self._validate_customer_record(connection, {"document_type": "批发销售单", "supplier": name})
                known = set(connection.execute(
                    select(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name)
                    .where(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name.in_(customer_names))
                ).scalars())
                known.update(connection.execute(
                    select(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name)
                    .where(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name.in_(customer_names))
                ).scalars())
                if unknown := customer_names - known:
                    missing.append(f"一般客户（一般客户管理）：{'、'.join(sorted(unknown))}")
            if accounting_subjects:
                known = set(connection.execute(
                    select(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.name)
                    .where(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.name.in_(accounting_subjects))
                ).scalars())
                if unknown := accounting_subjects - known:
                    missing.append(f"费用项目名/科目（科目管理）：{'、'.join(sorted(unknown))}")
            if missing:
                raise ValueError(f"模板中的以下档案不存在：{'；'.join(missing)}。请先在对应管理页面处理后再导入；本次未导入任何数据")
            for plan in active_plans:
                if not plan.get("details"):
                    label = f"{plan.get('date') or ''} {plan['document_type']}（摘要：{plan.get('summary') or ''}）"
                    raise ValueError(f"{label}：没有可导入的明细")
            document_sequences: dict[tuple[str, str], int] = {}
            written_document_ids: set[int] = set()
            pending_details: list[dict[str, object]] = []
            pending_document_ids: set[int] = set()
            for plan in plans:
                if plan.get("decision") == "skip":
                    skipped += 1
                    continue
                date_value = parse_date(plan["date"])
                label = f"{plan['date']} {plan['document_type']}（摘要：{plan['summary']}）"
                matched = connection.execute(
                    select(record_table)
                    .where(
                        record_table.c.deleted_at.is_(None),
                        or_(record_table.c.date_value == date_value, record_table.c.date == plan["date"]),
                        record_table.c.summary == plan["summary"],
                        record_table.c.document_type == plan["document_type"],
                        record_table.c.supplier == plan["supplier"],
                        or_(record_table.c.warehouse.is_(None), record_table.c.warehouse == "")
                        if not plan["warehouse"] else record_table.c.warehouse == plan["warehouse"],
                    )
                    .order_by(record_table.c.id.desc())
                ).mappings().first()
                decision = plan.get("decision")
                if matched and decision not in {"overwrite", "new"}:
                    raise ValueError(f"{label}：同日同摘要、同类型、同往来单位、同仓库单据已存在，请先确认覆盖或新增")
                if not matched and decision == "overwrite":
                    raise ValueError(f"{label}：目标单据已变化，请重新预检查")
                if not matched and decision == "new" and not plan.get("same_file_conflict"):
                    raise ValueError(f"{label}：冲突单据已变化，请重新预检查")
                if decision == "new":
                    new_summary = str(plan.get("new_summary") or "").strip()
                    if not new_summary or new_summary == plan["summary"]:
                        raise ValueError(f"{label}：新建单据必须修改摘要")
                    duplicate_summary = connection.execute(
                        select(record_table.c.id).where(
                            record_table.c.deleted_at.is_(None),
                            or_(record_table.c.date_value == date_value, record_table.c.date == plan["date"]),
                            record_table.c.document_type == plan["document_type"],
                            record_table.c.supplier == plan["supplier"],
                            or_(record_table.c.warehouse.is_(None), record_table.c.warehouse == "")
                            if not plan["warehouse"] else record_table.c.warehouse == plan["warehouse"],
                            record_table.c.summary == new_summary,
                        ).limit(1)
                    ).scalar_one_or_none()
                    if duplicate_summary is not None:
                        raise ValueError(f"{label}：修改后的摘要仍与已有单据重复")
                if matched and decision == "overwrite":
                    document_id = matched["id"]
                    if document_id in pending_document_ids:
                        self._insert_template_details(connection, pending_details)
                        pending_details.clear()
                        pending_document_ids.clear()
                    connection.execute(delete(detail_table).where(detail_table.c.document_id == document_id))
                    connection.execute(update(record_table).where(record_table.c.id == document_id).values(
                        warehouse=plan["warehouse"] or None,
                        handler=plan["handler"],
                        source_workbook=plan["source_workbook"],
                        source_sheet=plan["source_sheet"],
                        source_row_number="template",
                        raw_payload={"import_type": "universal_template", "brand": plan.get("brand") or ""},
                    ))
                    replaced += 1
                else:
                    generated_number = self._generate_document_number(
                        connection,
                        plan["date"],
                        plan["document_type"],
                        sequences=document_sequences,
                    )
                    payload = self._prepare_record({
                        "document_number": generated_number,
                        "date": plan["date"],
                        "document_type": plan["document_type"],
                        "supplier": plan["supplier"],
                        "warehouse": plan["warehouse"],
                        "handler": plan["handler"],
                        "summary": plan.get("new_summary") if decision == "new" else plan["summary"],
                        "source_workbook": plan["source_workbook"],
                        "source_sheet": plan["source_sheet"],
                        "source_row_number": "template",
                        "raw_payload": {
                            "import_type": "universal_template",
                            "brand": plan.get("brand") or "",
                        },
                    })
                    document_id = connection.execute(
                        insert(record_table).values(**payload).returning(record_table.c.id)
                    ).scalar_one()
                    created += 1
                for row in plan["details"]:
                    pending_details.append(dict(row, document_id=document_id))
                    pending_document_ids.add(document_id)
                    if len(pending_details) >= TEMPLATE_DETAIL_WRITE_BATCH_SIZE:
                        self._insert_template_details(connection, pending_details)
                        pending_details.clear()
                        pending_document_ids.clear()
                detail_count += len(plan["details"])
                written_document_ids.add(document_id)
            if pending_details:
                self._insert_template_details(connection, pending_details)
            self._update_template_totals(connection, sorted(written_document_ids))
            result = {"created": created, "replaced": replaced, "skipped": skipped, "details": detail_count}
            if task_id is not None:
                complete_inventory_import(connection, task_id, result)
        return result

    @staticmethod
    def _insert_template_details(connection, rows: list[dict[str, object]]) -> None:
        table = INVENTORY_DETAIL_TABLE
        for _, grouped_rows in groupby(rows, key=lambda row: frozenset(row)):
            batch = list(grouped_rows)
            if (
                connection.dialect.name != "postgresql"
                or connection.dialect.driver != "psycopg"
                or len(batch) < TEMPLATE_DETAIL_COPY_MIN_ROWS
            ):
                connection.execute(insert(table), batch)
                continue
            columns = tuple(batch[0])
            json_columns = {name for name in columns if isinstance(table.c[name].type, JSON)}
            table_name = sql.Identifier(table.schema, table.name) if table.schema else sql.Identifier(table.name)
            statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
                table_name,
                sql.SQL(", ").join(map(sql.Identifier, columns)),
            )
            try:
                with connection.connection.driver_connection.cursor() as cursor:
                    with cursor.copy(statement) as writer:
                        for row in batch:
                            writer.write_row(tuple(
                                Json(row[name], dumps=_json_serializer) if name in json_columns else row[name]
                                for name in columns
                            ))
            except PsycopgError as error:
                raise DBAPIError.instance(
                    statement.as_string(), None, error, connection.dialect.dbapi.Error,
                    hide_parameters=True, dialect=connection.dialect,
                ) from error

    @staticmethod
    def _update_template_totals(connection, document_ids: list[int], *, coalesce_empty: bool = False) -> None:
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        for offset in range(0, len(document_ids), TEMPLATE_TOTALS_BATCH_SIZE):
            totals = (
                select(
                    detail.c.document_id,
                    func.sum(detail.c.quantity).label("quantity"),
                    func.sum(detail.c.amount).label("amount"),
                )
                .where(detail.c.document_id.in_(document_ids[offset:offset + TEMPLATE_TOTALS_BATCH_SIZE]))
                .group_by(detail.c.document_id)
                .subquery()
            )
            quantity = func.coalesce(totals.c.quantity, 0) if coalesce_empty else totals.c.quantity
            amount = func.coalesce(totals.c.amount, 0) if coalesce_empty else totals.c.amount
            connection.execute(
                update(record)
                .where(record.c.id == totals.c.document_id)
                .values(
                    total_count=case(
                        (record.c.document_type.in_(ACCOUNTING_DOCUMENT_TYPES), None),
                        (record.c.document_type.in_(NEGATIVE_TOTAL_DOCUMENT_TYPES), -func.abs(quantity)),
                        else_=quantity,
                    ),
                    amount=case(
                        (record.c.document_type.in_(NEGATIVE_TOTAL_DOCUMENT_TYPES), -func.abs(amount)),
                        else_=amount,
                    ),
                )
            )

    def create_record(self, record: Mapping[str, object]) -> dict[str, object]:
        table = INVENTORY_TABLE
        with self.engine.begin() as connection:
            payload = self._prepare_record(record)
            self._validate_customer_record(connection, payload)
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
            before = connection.execute(select(table).where(table.c.id == record_id)).mappings().first()
            if before is None:
                return None
            if (
                payload.get("supplier", before["supplier"]) != before["supplier"]
                or payload.get("document_type", before["document_type"]) != before["document_type"]
            ):
                self._validate_customer_record(connection, {**before, **payload})
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        item = dict(row)
        if "document_type" in payload:
            self.recalculate_totals(record_id)
            return self.get_record(record_id) or item
        return item

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
        record_ids = list(dict.fromkeys(ids))
        deleted = 0
        with self.engine.begin() as connection:
            for offset in range(0, len(record_ids), 1000):
                result = connection.execute(
                    update(table)
                    .where(table.c.id.in_(record_ids[offset:offset + 1000]), table.c.deleted_at.is_(None))
                    .values(deleted_at=func.now())
                )
                deleted += result.rowcount
        return deleted

    def get_records_by_ids(self, ids: list[int]) -> list[dict[str, object]]:
        table = INVENTORY_TABLE
        record_ids = list(dict.fromkeys(ids))
        records = []
        with self.engine.connect() as connection:
            for offset in range(0, len(record_ids), 1000):
                records.extend(dict(row) for row in connection.execute(
                    select(table).where(table.c.id.in_(record_ids[offset:offset + 1000]), table.c.deleted_at.is_(None))
                ).mappings())
        return records

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
        ledger_amount = func.abs(effective_amount)
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
            (table.c.document_type.in_(increase_types), ledger_amount),
            else_=0,
        )
        decrease_expr = case(
            (table.c.document_type.in_(decrease_types), ledger_amount),
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

    def list_supplier_brands(self) -> list[dict[str, object]]:
        statement = select(SUPPLIER_BRAND_TABLE).order_by(SUPPLIER_BRAND_TABLE.c.sort_order, SUPPLIER_BRAND_TABLE.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def get_supplier_brand(self, brand_id: int) -> dict[str, object] | None:
        statement = select(SUPPLIER_BRAND_TABLE).where(SUPPLIER_BRAND_TABLE.c.id == brand_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_supplier_brand_by_code(self, code: str) -> dict[str, object] | None:
        statement = select(SUPPLIER_BRAND_TABLE).where(SUPPLIER_BRAND_TABLE.c.code == code)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def list_product_archive_brands(self) -> list[dict[str, object]]:
        statement = (
            select(SUPPLIER_BRAND_TABLE)
            .where(SUPPLIER_BRAND_TABLE.c.product_archive_enabled.is_(True))
            .order_by(SUPPLIER_BRAND_TABLE.c.sort_order, SUPPLIER_BRAND_TABLE.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_supplier_brand(self, data: Mapping[str, object]) -> dict[str, object]:
        name = str(data.get("name") or "").strip()
        code = str(data.get("code") or "").strip() or f"supplier_brand_{uuid4().hex[:12]}"
        with self.engine.begin() as connection:
            sort_order = connection.execute(select(func.coalesce(func.max(SUPPLIER_BRAND_TABLE.c.sort_order), 0))).scalar_one() + 1
            row = connection.execute(
                insert(SUPPLIER_BRAND_TABLE)
                .values(code=code, name=name, product_archive_enabled=True, sort_order=sort_order)
                .returning(SUPPLIER_BRAND_TABLE)
            ).mappings().one()
            item = dict(row)
            row = connection.execute(
                update(SUPPLIER_BRAND_TABLE)
                .where(SUPPLIER_BRAND_TABLE.c.id == item["id"])
                .values(product_table_name=allocate_product_table_name(connection, name, item["id"]))
                .returning(SUPPLIER_BRAND_TABLE)
            ).mappings().one()
        return dict(row)

    def update_supplier_brand(self, brand_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        name = str(data.get("name") or "").strip()
        with self.engine.begin() as connection:
            row = connection.execute(
                update(SUPPLIER_BRAND_TABLE)
                .where(SUPPLIER_BRAND_TABLE.c.id == brand_id)
                .values(name=name)
                .returning(SUPPLIER_BRAND_TABLE)
            ).mappings().first()
        return None if row is None else dict(row)

    def delete_supplier_brand(self, brand_id: int) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                delete(SUPPLIER_BRAND_TABLE)
                .where(SUPPLIER_BRAND_TABLE.c.id == brand_id)
                .returning(SUPPLIER_BRAND_TABLE)
            ).mappings().first()
        return None if row is None else dict(row)

    def count_suppliers_by_brand(self, brand_code: str) -> int:
        statement = (
            select(func.count())
            .select_from(SUPPLIER_TABLE)
            .where(SUPPLIER_TABLE.c.brand == brand_code)
        )
        with self.engine.connect() as connection:
            return int(connection.execute(statement).scalar_one())

    def reorder_supplier_brands(self, ordered_ids: list[int]) -> bool:
        return self._replace_sort_order(SUPPLIER_BRAND_TABLE, ordered_ids)

    def list_suppliers(self, *, brand: str | None = None) -> list[dict[str, object]]:
        statement = select(SUPPLIER_TABLE).order_by(SUPPLIER_TABLE.c.brand, SUPPLIER_TABLE.c.id)
        if brand:
            statement = statement.where(SUPPLIER_TABLE.c.brand == brand)
        with self.engine.begin() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def list_suppliers_page(
        self,
        *,
        page: int,
        page_size: int,
        query: str | None = None,
        brand: str | None = None,
        include_balances: bool = False,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> dict[str, object]:
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
        with self.engine.begin() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]
            if include_balances and items:
                balances = self._supplier_balance_summaries(
                    connection,
                    [str(item["name"]) for item in items],
                    date_start=date_start,
                    date_end=date_end,
                )
                for item in items:
                    item.update(balances.get(str(item["name"]), {
                        "beginning_balance": "0", "period_amount": "0", "ending_balance": "0",
                    }))
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _supplier_balance_summaries(
        self,
        connection,
        names: list[str],
        *,
        date_start: str | None,
        date_end: str | None,
    ) -> dict[str, dict[str, str]]:
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        start_date = parse_date(date_start) if date_start else None
        end_date = parse_date(date_end) if date_end else None
        detail_record = record.alias("supplier_balance_record")
        detail_amount = (
            select(
                detail.c.document_id.label("document_id"),
                func.coalesce(func.sum(detail.c.amount), 0).label("detail_amount"),
            )
            .select_from(detail.join(detail_record, detail_record.c.id == detail.c.document_id))
            .where(detail_record.c.supplier.in_(names))
            .where(detail_record.c.date_value <= end_date if end_date else True)
            .group_by(detail.c.document_id)
            .subquery()
        )
        amount = func.abs(func.coalesce(detail_amount.c.detail_amount, record.c.amount, 0))
        signed_amount = case(
            (record.c.document_type.in_(SUPPLIER_LEDGER_INCREASE_TYPES), amount),
            (record.c.document_type.in_(SUPPLIER_LEDGER_DECREASE_TYPES), -amount),
            else_=0,
        )
        record_date = record.c.date_value
        beginning = func.coalesce(func.sum(case((record_date < start_date, signed_amount), else_=0)), 0) if start_date else func.cast(0, record.c.amount.type)
        period_conditions = []
        if start_date:
            period_conditions.append(record_date >= start_date)
        if end_date:
            period_conditions.append(record_date <= end_date)
        period = (
            func.coalesce(func.sum(case((and_(*period_conditions), signed_amount), else_=0)), 0)
            if period_conditions else func.coalesce(func.sum(signed_amount), 0)
        )
        statement = (
            select(record.c.supplier, beginning.label("beginning_balance"), period.label("period_amount"))
            .outerjoin(detail_amount, detail_amount.c.document_id == record.c.id)
            .where(
                record.c.deleted_at.is_(None),
                record.c.supplier.in_(names),
                record.c.document_type.in_((*SUPPLIER_LEDGER_INCREASE_TYPES, *SUPPLIER_LEDGER_DECREASE_TYPES)),
                record.c.date_value <= end_date if end_date else True,
            )
            .group_by(record.c.supplier)
        )
        summaries = {}
        for row in connection.execute(statement).mappings():
            opening = Decimal(str(row["beginning_balance"] or 0))
            change = Decimal(str(row["period_amount"] or 0))
            summaries[row["supplier"]] = {
                "beginning_balance": self._format_decimal(opening),
                "period_amount": self._format_decimal(change),
                "ending_balance": self._format_decimal(opening + change),
            }
        return summaries

    def list_supplier_factory_code_conflicts(self, factory_code: str, *, brand: str) -> list[dict[str, object]]:
        normalized_code = factory_code.strip()
        if not normalized_code:
            return []
        statement = (
            select(SUPPLIER_TABLE.c.brand, SUPPLIER_TABLE.c.name, SUPPLIER_BRAND_TABLE.c.name.label("brand_name"))
            .select_from(SUPPLIER_TABLE.outerjoin(SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE.c.brand == SUPPLIER_BRAND_TABLE.c.code))
            .where(SUPPLIER_TABLE.c.factory_code == normalized_code, SUPPLIER_TABLE.c.brand != brand)
            .order_by(SUPPLIER_TABLE.c.brand, SUPPLIER_TABLE.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_supplier(self, data: Mapping[str, object]) -> dict[str, object]:
        statement = insert(SUPPLIER_TABLE).values(**self._prepare_supplier(data)).returning(SUPPLIER_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def update_supplier(self, supplier_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            before = connection.execute(
                select(SUPPLIER_TABLE)
                .where(SUPPLIER_TABLE.c.id == supplier_id)
                .with_for_update()
            ).mappings().first()
            if before is None:
                return None

            payload = self._prepare_supplier({**before, **data})

            row = connection.execute(
                update(SUPPLIER_TABLE)
                .where(SUPPLIER_TABLE.c.id == supplier_id)
                .values(**payload)
                .returning(SUPPLIER_TABLE)
            ).mappings().one()

            previous_name = str(before.get("name") or "").strip()
            current_name = str(row.get("name") or "").strip()
            if previous_name and current_name and previous_name != current_name:
                self._rename_product_archive_supplier(
                    connection,
                    brand=str(before.get("brand") or "").strip(),
                    previous_name=previous_name,
                    current_name=current_name,
                )
                self._rename_inventory_supplier_references(
                    connection,
                    previous_name=previous_name,
                    current_name=current_name,
                )
        return None if row is None else dict(row)

    @staticmethod
    def _rename_product_archive_supplier(
        connection,
        *,
        brand: str,
        previous_name: str,
        current_name: str,
    ) -> int:
        if brand == EBLAN_WOMENS_SUPPLIER_BRAND:
            brand = EBLAN_BRAND
        product_table = PRODUCT_ARCHIVE_TABLES.get(brand)
        if product_table is None:
            table_name = connection.execute(
                select(SUPPLIER_BRAND_TABLE.c.product_table_name)
                .where(SUPPLIER_BRAND_TABLE.c.code == brand)
                .where(SUPPLIER_BRAND_TABLE.c.product_archive_enabled.is_(True))
            ).scalar_one_or_none()
            normalized_table_name = manual_product_table_name(table_name)
            if normalized_table_name is None or not inspect(connection).has_table(normalized_table_name):
                return 0
            product_table = Table(normalized_table_name, MetaData(), autoload_with=connection)

        result = connection.execute(
            update(product_table)
            .where(func.btrim(product_table.c.supplier_name) == previous_name)
            .values(
                supplier_name=current_name,
                updated_at=func.date_trunc("minute", func.now()),
            )
        )
        return result.rowcount or 0

    @staticmethod
    def _rename_inventory_supplier_references(
        connection,
        *,
        previous_name: str,
        current_name: str,
    ) -> int:
        result = connection.execute(
            update(INVENTORY_TABLE)
            .where(
                func.btrim(INVENTORY_TABLE.c.supplier) == previous_name,
                or_(
                    INVENTORY_TABLE.c.document_type.is_(None),
                    INVENTORY_TABLE.c.document_type.not_in(NON_SUPPLIER_COUNTERPARTY_TYPES),
                ),
            )
            .values(
                supplier=current_name,
                updated_at=func.date_trunc("minute", func.now()),
            )
        )
        return result.rowcount or 0

    def get_supplier(self, supplier_id: int) -> dict[str, object] | None:
        statement = select(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == supplier_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def delete_supplier(self, supplier_id: int) -> bool:
        statement = delete(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.id == supplier_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    def list_suppliers_by_exact_name(self, name: str) -> list[dict[str, object]]:
        statement = select(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.name == name).order_by(SUPPLIER_TABLE.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def get_supplier_by_name(self, name: str, brand: str | None = None) -> dict[str, object] | None:
        statement = select(SUPPLIER_TABLE).where(SUPPLIER_TABLE.c.name == name)
        if brand:
            statement = statement.where(SUPPLIER_TABLE.c.brand == brand)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
            if row is None:
                normalized_name = str(name or "").strip().replace("（", "(").replace("）", ")").lower()
                if normalized_name:
                    normalized_supplier_name = func.lower(
                        func.replace(
                            func.replace(SUPPLIER_TABLE.c.name, "（", "("),
                            "）",
                            ")",
                        )
                    )
                    normalized_statement = select(SUPPLIER_TABLE).where(normalized_supplier_name == normalized_name)
                    if brand:
                        normalized_statement = normalized_statement.where(SUPPLIER_TABLE.c.brand == brand)
                    row = connection.execute(normalized_statement).mappings().first()
        return None if row is None else dict(row)

    @staticmethod
    def _next_sort_order(connection, table, where_clause=None) -> int:
        statement = select(func.coalesce(func.max(table.c.sort_order), 0))
        if where_clause is not None:
            statement = statement.where(where_clause)
        return int(connection.execute(statement).scalar_one() or 0) + 1

    def _replace_sort_order(self, table, ordered_ids: list[int], where_clause=None) -> bool:
        if len(ordered_ids) != len(set(ordered_ids)):
            return False
        statement = select(table.c.id)
        if where_clause is not None:
            statement = statement.where(where_clause)
        with self.engine.begin() as connection:
            existing_ids = [int(row[0]) for row in connection.execute(statement).all()]
            if set(existing_ids) != set(ordered_ids):
                return False
            for sort_order, item_id in enumerate(ordered_ids, start=1):
                connection.execute(
                    update(table)
                    .where(table.c.id == item_id)
                    .values(sort_order=sort_order)
                )
        return True

    # ── General Customer Brands & Shops ────────────────────────────

    def _general_customer_sort_orders(
        self,
        user_id: int | None,
        scope: str,
    ) -> dict[tuple[int, int], int]:
        if user_id is None:
            return {}
        statement = select(
            GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.parent_id,
            GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.item_id,
            GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.sort_order,
        ).where(
            GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.user_id == user_id,
            GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.scope == scope,
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return {
                (int(row["parent_id"]), int(row["item_id"])): int(row["sort_order"])
                for row in rows
            }

    @staticmethod
    def _general_customer_sort_key(
        preferences: Mapping[tuple[int, int], int],
        parent_id: int,
        item_id: int,
        default_sort_order: int,
    ) -> tuple[int, int, int]:
        preference_order = preferences.get((parent_id, item_id))
        if preference_order is not None:
            return (0, preference_order, item_id)
        return (1, default_sort_order, item_id)

    def _replace_general_customer_user_sort_order(
        self,
        *,
        user_id: int,
        scope: str,
        parent_id: int,
        table,
        ordered_ids: list[int],
        condition=None,
    ) -> bool:
        statement = select(table.c.id)
        if condition is not None:
            statement = statement.where(condition)
        with self.engine.begin() as connection:
            existing_ids = [int(value) for value in connection.execute(statement).scalars()]
            if set(existing_ids) != set(ordered_ids):
                return False
            connection.execute(
                delete(GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE).where(
                    GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.user_id == user_id,
                    GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.scope == scope,
                    GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.c.parent_id == parent_id,
                )
            )
            connection.execute(
                insert(GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE),
                [
                    {
                        "user_id": user_id,
                        "scope": scope,
                        "parent_id": parent_id,
                        "item_id": item_id,
                        "sort_order": sort_order,
                    }
                    for sort_order, item_id in enumerate(ordered_ids, start=1)
                ],
            )
        return True

    def list_inventory_brand_options(self) -> list[dict[str, str]]:
        with self.engine.connect() as connection:
            warehouse_brands = connection.execute(
                select(WAREHOUSE_BRAND_TABLE.c.name)
                .order_by(WAREHOUSE_BRAND_TABLE.c.sort_order, WAREHOUSE_BRAND_TABLE.c.id)
            ).scalars().all()
            warehouse_brands.extend(connection.execute(select(WAREHOUSE_TABLE.c.brand).distinct()).scalars())
            supplier_brands = [dict(row) for row in connection.execute(
                select(SUPPLIER_BRAND_TABLE.c.code, SUPPLIER_BRAND_TABLE.c.name)
                .order_by(SUPPLIER_BRAND_TABLE.c.sort_order, SUPPLIER_BRAND_TABLE.c.id)
            ).mappings()]
            configured_codes = {brand["code"] for brand in supplier_brands}
            supplier_brands.extend(
                {"code": code, "name": ""}
                for code in connection.execute(select(SUPPLIER_TABLE.c.brand).distinct()).scalars()
                if code not in configured_codes
            )
            customer_brands = connection.execute(
                select(GENERAL_CUSTOMER_BRAND_TABLE.c.name)
                .order_by(GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order, GENERAL_CUSTOMER_BRAND_TABLE.c.id)
            ).scalars().all()
            customer_brands.extend(connection.execute(select(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name).distinct()).scalars())
        return inventory_brand_options(warehouse_brands, supplier_brands, customer_brands)

    def list_general_customer_brands(self, user_id: int | None = None) -> list[dict[str, object]]:
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
                GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order,
                GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
                GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
                func.coalesce(shop_count.c.shop_count, 0).label("shop_count"),
            )
            .outerjoin(shop_count, shop_count.c.brand_name == GENERAL_CUSTOMER_BRAND_TABLE.c.name)
            .order_by(GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order, GENERAL_CUSTOMER_BRAND_TABLE.c.id)
        )
        with self.engine.connect() as connection:
            items = [dict(row) for row in connection.execute(statement).mappings()]
        preferences = self._general_customer_sort_orders(user_id, GENERAL_CUSTOMER_SORT_SCOPE_BRAND)
        return sorted(
            items,
            key=lambda item: self._general_customer_sort_key(
                preferences,
                GENERAL_CUSTOMER_ROOT_SORT_PARENT_ID,
                int(item["id"]),
                int(item["sort_order"]),
            ),
        )

    def create_general_customer_brand(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "name": str(data.get("name") or "").strip(),
        }
        with self.engine.begin() as connection:
            payload["sort_order"] = self._next_sort_order(connection, GENERAL_CUSTOMER_BRAND_TABLE)
            statement = (
                insert(GENERAL_CUSTOMER_BRAND_TABLE)
                .values(**payload)
                .returning(
                    GENERAL_CUSTOMER_BRAND_TABLE.c.id,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.name,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
                    GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
                )
            )
            row = connection.execute(statement).mappings().one()
        item = dict(row)
        item["shop_count"] = 0
        return item

    def get_general_customer_brand(self, brand_id: int) -> dict[str, object] | None:
        shop_count = (
            select(func.count())
            .select_from(GENERAL_CUSTOMER_SHOP_TABLE)
            .where(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == GENERAL_CUSTOMER_BRAND_TABLE.c.name)
            .scalar_subquery()
        )
        statement = select(
            GENERAL_CUSTOMER_BRAND_TABLE.c.id,
            GENERAL_CUSTOMER_BRAND_TABLE.c.name,
            GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order,
            GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
            GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
            shop_count.label("shop_count"),
        ).where(GENERAL_CUSTOMER_BRAND_TABLE.c.id == brand_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def update_general_customer_brand(self, brand_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = {
            "name": str(data.get("name") or "").strip(),
        }
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
            connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.id)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == brand_name)
                .with_for_update()
            ).all()
            has_history = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.id).where(
                    GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == brand_name,
                    self._general_customer_shop_history_condition(),
                ).limit(1)
            ).first()
            if has_history is not None:
                raise ValueError("该品牌下有历史业务，请停用相关店铺，不能删除品牌")
            connection.execute(delete(GENERAL_CUSTOMER_SHOP_TABLE).where(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == brand_name))
            result = connection.execute(delete(GENERAL_CUSTOMER_BRAND_TABLE).where(GENERAL_CUSTOMER_BRAND_TABLE.c.id == brand_id))
        return None if result.rowcount > 0 else "not_found"

    def get_general_customer_brand_by_name(self, name: str) -> dict[str, object] | None:
        statement = select(
            GENERAL_CUSTOMER_BRAND_TABLE.c.id,
            GENERAL_CUSTOMER_BRAND_TABLE.c.name,
            GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order,
            GENERAL_CUSTOMER_BRAND_TABLE.c.created_at,
            GENERAL_CUSTOMER_BRAND_TABLE.c.updated_at,
        ).where(GENERAL_CUSTOMER_BRAND_TABLE.c.name == name)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def list_general_customer_shops(self, user_id: int | None = None) -> list[dict[str, object]]:
        # Build the set once rather than scanning business records separately
        # for every shop and child unit. Deleted records still count as history.
        history_names = (
            select(func.trim(INVENTORY_TABLE.c.supplier).label("name"))
            .where(INVENTORY_TABLE.c.supplier.is_not(None))
            .distinct()
            .cte("customer_shop_history_names")
        )
        shops_with_unit_history = (
            select(GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id)
            .join(history_names, func.trim(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name) == history_names.c.name)
        )
        has_history = func.coalesce(or_(
            func.trim(GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name).in_(select(history_names.c.name)),
            GENERAL_CUSTOMER_SHOP_TABLE.c.id.in_(shops_with_unit_history),
        ), False)
        unit_count = (
            select(
                GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id,
                func.count(GENERAL_CUSTOMER_UNIT_TABLE.c.id).label("unit_count"),
            )
            .group_by(GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id)
            .subquery()
        )
        statement = (
            select(
                GENERAL_CUSTOMER_SHOP_TABLE.c.id,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.is_active,
                has_history.label("has_history"),
                GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order,
                GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
                GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
                GENERAL_CUSTOMER_BRAND_TABLE.c.id.label("_brand_id"),
                GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order.label("_brand_sort_order"),
                func.coalesce(unit_count.c.unit_count, 0).label("unit_count"),
            )
            .outerjoin(unit_count, unit_count.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
            .outerjoin(
                GENERAL_CUSTOMER_BRAND_TABLE,
                GENERAL_CUSTOMER_BRAND_TABLE.c.name == GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
            )
            .order_by(
                GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order,
                GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order,
                GENERAL_CUSTOMER_SHOP_TABLE.c.id,
            )
        )
        with self.engine.connect() as connection:
            items = [dict(row) for row in connection.execute(statement).mappings()]
        brand_preferences = self._general_customer_sort_orders(user_id, GENERAL_CUSTOMER_SORT_SCOPE_BRAND)
        shop_preferences = self._general_customer_sort_orders(user_id, GENERAL_CUSTOMER_SORT_SCOPE_SHOP)
        items.sort(
            key=lambda item: (
                self._general_customer_sort_key(
                    brand_preferences,
                    GENERAL_CUSTOMER_ROOT_SORT_PARENT_ID,
                    int(item["_brand_id"]),
                    int(item["_brand_sort_order"]),
                ),
                self._general_customer_sort_key(
                    shop_preferences,
                    int(item["_brand_id"]),
                    int(item["id"]),
                    int(item["sort_order"]),
                ),
            )
        )
        for item in items:
            item.pop("_brand_id", None)
            item.pop("_brand_sort_order", None)
        return items

    def create_general_customer_shop(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "customer_name": str(data.get("customer_name") or "").strip(),
            "shop_name": str(data.get("shop_name") or "").strip(),
        }
        with self.engine.begin() as connection:
            self._ensure_general_customer_brand(connection, payload["customer_name"])
            payload["sort_order"] = self._next_sort_order(
                connection,
                GENERAL_CUSTOMER_SHOP_TABLE,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == payload["customer_name"],
            )
            statement = (
                insert(GENERAL_CUSTOMER_SHOP_TABLE)
                .values(**payload)
                .returning(
                    GENERAL_CUSTOMER_SHOP_TABLE.c.id,
                    GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                    GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                    GENERAL_CUSTOMER_SHOP_TABLE.c.is_active,
                    GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order,
                    GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
                    GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
                )
            )
            row = connection.execute(statement).mappings().one()
        item = dict(row)
        item["unit_count"] = 0
        item["has_history"] = False
        return item

    def get_general_customer_shop(self, shop_id: int) -> dict[str, object] | None:
        unit_count = (
            select(func.count())
            .select_from(GENERAL_CUSTOMER_UNIT_TABLE)
            .where(GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
            .scalar_subquery()
        )
        statement = select(
            GENERAL_CUSTOMER_SHOP_TABLE.c.id,
            GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.is_active,
            self._general_customer_shop_history_condition().label("has_history"),
            GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order,
            GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
            GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
            unit_count.label("unit_count"),
        ).where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def reorder_general_customer_brands(self, user_id: int, ordered_ids: list[int]) -> bool:
        return self._replace_general_customer_user_sort_order(
            user_id=user_id,
            scope=GENERAL_CUSTOMER_SORT_SCOPE_BRAND,
            parent_id=GENERAL_CUSTOMER_ROOT_SORT_PARENT_ID,
            table=GENERAL_CUSTOMER_BRAND_TABLE,
            ordered_ids=ordered_ids,
        )

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
            is_active = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.is_active)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id).with_for_update()
            ).scalar_one_or_none()
            if is_active is False:
                raise ValueError("店铺已停用，请先启用店铺后再编辑")
            self._ensure_general_customer_brand(connection, payload["customer_name"])
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        return self.get_general_customer_shop(shop_id)

    def delete_general_customer_shop(self, shop_id: int) -> bool:
        with self.engine.begin() as connection:
            shop = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.id)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id).with_for_update()
            ).first()
            if shop is None:
                return False
            has_history = connection.execute(
                select(self._general_customer_shop_history_condition())
                .select_from(GENERAL_CUSTOMER_SHOP_TABLE)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id)
            ).scalar_one()
            if has_history:
                statement = update(GENERAL_CUSTOMER_SHOP_TABLE).values(is_active=False)
            else:
                statement = delete(GENERAL_CUSTOMER_SHOP_TABLE)
            statement = statement.where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id)
            result = connection.execute(statement)
        return result.rowcount > 0

    @staticmethod
    def _general_customer_shop_history_condition():
        shop = GENERAL_CUSTOMER_SHOP_TABLE
        unit_names = (
            select(func.trim(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name))
            .where(GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == shop.c.id)
            .correlate(shop)
        )
        return (
            select(INVENTORY_TABLE.c.id)
            .where(or_(
                func.trim(INVENTORY_TABLE.c.supplier) == func.trim(shop.c.shop_name),
                func.trim(INVENTORY_TABLE.c.supplier).in_(unit_names),
            ))
            .correlate(shop)
            .exists()
        )

    def set_general_customer_shop_status(self, shop_id: int, *, is_active: bool) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(GENERAL_CUSTOMER_SHOP_TABLE)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == shop_id)
                .values(is_active=is_active)
            )
            if result.rowcount == 0:
                return None
        return self.get_general_customer_shop(shop_id)

    def validate_customer_record(self, record: Mapping[str, object]) -> None:
        with self.engine.connect() as connection:
            self._validate_customer_record(connection, record)

    @staticmethod
    def _validate_customer_record(connection, record: Mapping[str, object]) -> None:
        if record.get("document_type") not in (*CUSTOMER_LEDGER_INCREASE_TYPES, *CUSTOMER_LEDGER_DECREASE_TYPES):
            return
        name = str(record.get("supplier") or "").strip()
        if not name:
            return
        shop = GENERAL_CUSTOMER_SHOP_TABLE
        matches = connection.execute(
            select(shop.c.is_active)
            .select_from(shop.outerjoin(GENERAL_CUSTOMER_UNIT_TABLE, GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == shop.c.id))
            .where(or_(
                func.trim(shop.c.shop_name) == name,
                func.trim(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name) == name,
            ))
            .with_for_update(of=shop)
        ).scalars().all()
        if matches and not any(matches):
            raise ValueError(f"一般客户“{name}”所属店铺已停用，请先启用店铺后再新增业务")

    def get_general_customer_shop_by_name(self, customer_name: str, shop_name: str) -> dict[str, object] | None:
        statement = select(
            GENERAL_CUSTOMER_SHOP_TABLE.c.id,
            GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order,
            GENERAL_CUSTOMER_SHOP_TABLE.c.created_at,
            GENERAL_CUSTOMER_SHOP_TABLE.c.updated_at,
        ).where(
            GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == customer_name,
            GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name == shop_name,
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def is_internal_sales_customer(self, name: object) -> bool:
        customer_name = str(name or "").strip()
        if not customer_name:
            return False
        statement = (
            select(GENERAL_CUSTOMER_SHOP_TABLE.c.id)
            .outerjoin(
                GENERAL_CUSTOMER_UNIT_TABLE,
                GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id,
            )
            .where(
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name.ilike("%内销客户%"),
                or_(
                    GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name == customer_name,
                    GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name == customer_name,
                ),
            )
            .limit(1)
        )
        with self.engine.connect() as connection:
            return connection.execute(statement).first() is not None

    def allows_zero_price_sales_customer(self, name: object) -> bool:
        customer_name = str(name or "").strip()
        if not customer_name:
            return False
        normalized_name = "".join(customer_name.split())
        return "总部采购" in normalized_name or self.is_internal_sales_customer(customer_name)

    def reorder_general_customer_shops(self, user_id: int, customer_name: str, ordered_ids: list[int]) -> bool:
        with self.engine.connect() as connection:
            brand_id = connection.execute(
                select(GENERAL_CUSTOMER_BRAND_TABLE.c.id).where(
                    GENERAL_CUSTOMER_BRAND_TABLE.c.name == customer_name
                )
            ).scalar_one_or_none()
        if brand_id is None:
            return False
        return self._replace_general_customer_user_sort_order(
            user_id=user_id,
            scope=GENERAL_CUSTOMER_SORT_SCOPE_SHOP,
            parent_id=int(brand_id),
            table=GENERAL_CUSTOMER_SHOP_TABLE,
            ordered_ids=ordered_ids,
            condition=GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == customer_name,
        )

    def list_general_customer_units(self, user_id: int | None = None) -> list[dict[str, object]]:
        statement = (
            select(
                GENERAL_CUSTOMER_UNIT_TABLE.c.id,
                GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id,
                GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name,
                GENERAL_CUSTOMER_UNIT_TABLE.c.sort_order,
                GENERAL_CUSTOMER_UNIT_TABLE.c.created_at,
                GENERAL_CUSTOMER_UNIT_TABLE.c.updated_at,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.is_active.label("shop_is_active"),
                GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order.label("_shop_sort_order"),
                GENERAL_CUSTOMER_BRAND_TABLE.c.id.label("_brand_id"),
                GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order.label("_brand_sort_order"),
            )
            .join(GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
            .join(GENERAL_CUSTOMER_BRAND_TABLE, GENERAL_CUSTOMER_BRAND_TABLE.c.name == GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name)
            .order_by(
                GENERAL_CUSTOMER_BRAND_TABLE.c.sort_order,
                GENERAL_CUSTOMER_SHOP_TABLE.c.sort_order,
                GENERAL_CUSTOMER_UNIT_TABLE.c.sort_order,
                GENERAL_CUSTOMER_UNIT_TABLE.c.id,
            )
        )
        with self.engine.connect() as connection:
            items = [dict(row) for row in connection.execute(statement).mappings()]
        brand_preferences = self._general_customer_sort_orders(user_id, GENERAL_CUSTOMER_SORT_SCOPE_BRAND)
        shop_preferences = self._general_customer_sort_orders(user_id, GENERAL_CUSTOMER_SORT_SCOPE_SHOP)
        unit_preferences = self._general_customer_sort_orders(user_id, GENERAL_CUSTOMER_SORT_SCOPE_UNIT)
        items.sort(
            key=lambda item: (
                self._general_customer_sort_key(
                    brand_preferences,
                    GENERAL_CUSTOMER_ROOT_SORT_PARENT_ID,
                    int(item["_brand_id"]),
                    int(item["_brand_sort_order"]),
                ),
                self._general_customer_sort_key(
                    shop_preferences,
                    int(item["_brand_id"]),
                    int(item["shop_id"]),
                    int(item["_shop_sort_order"]),
                ),
                self._general_customer_sort_key(
                    unit_preferences,
                    int(item["shop_id"]),
                    int(item["id"]),
                    int(item["sort_order"]),
                ),
            )
        )
        for item in items:
            item.pop("_brand_id", None)
            item.pop("_brand_sort_order", None)
            item.pop("_shop_sort_order", None)
        return items

    def create_general_customer_unit(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "shop_id": int(data.get("shop_id") or 0),
            "unit_name": str(data.get("unit_name") or "").strip(),
        }
        with self.engine.begin() as connection:
            is_active = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.is_active)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == payload["shop_id"])
                .with_for_update()
            ).scalar_one_or_none()
            if is_active is False:
                raise ValueError("所属店铺已停用，请先启用店铺后再新增单位")
            payload["sort_order"] = self._next_sort_order(
                connection,
                GENERAL_CUSTOMER_UNIT_TABLE,
                GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == payload["shop_id"],
            )
            statement = insert(GENERAL_CUSTOMER_UNIT_TABLE).values(**payload).returning(GENERAL_CUSTOMER_UNIT_TABLE)
            row = connection.execute(statement).mappings().one()
            shop = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name, GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name, GENERAL_CUSTOMER_SHOP_TABLE.c.is_active.label("shop_is_active"))
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == payload["shop_id"])
            ).mappings().one()
        item = dict(row)
        item.update(shop)
        return item

    def get_general_customer_unit(self, unit_id: int) -> dict[str, object] | None:
        statement = (
            select(
                GENERAL_CUSTOMER_UNIT_TABLE.c.id,
                GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id,
                GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name,
                GENERAL_CUSTOMER_UNIT_TABLE.c.sort_order,
                GENERAL_CUSTOMER_UNIT_TABLE.c.created_at,
                GENERAL_CUSTOMER_UNIT_TABLE.c.updated_at,
                GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name,
                GENERAL_CUSTOMER_SHOP_TABLE.c.is_active.label("shop_is_active"),
            )
            .join(GENERAL_CUSTOMER_SHOP_TABLE, GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
            .where(GENERAL_CUSTOMER_UNIT_TABLE.c.id == unit_id)
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_general_customer_unit_by_name(self, shop_id: int, unit_name: str) -> dict[str, object] | None:
        statement = select(GENERAL_CUSTOMER_UNIT_TABLE).where(
            GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == shop_id,
            GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name == unit_name,
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def reorder_general_customer_units(self, user_id: int, shop_id: int, ordered_ids: list[int]) -> bool:
        return self._replace_general_customer_user_sort_order(
            user_id=user_id,
            scope=GENERAL_CUSTOMER_SORT_SCOPE_UNIT,
            parent_id=shop_id,
            table=GENERAL_CUSTOMER_UNIT_TABLE,
            ordered_ids=ordered_ids,
            condition=GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == shop_id,
        )

    def update_general_customer_unit(self, unit_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = {
            "shop_id": int(data.get("shop_id") or 0),
            "unit_name": str(data.get("unit_name") or "").strip(),
        }
        statement = (
            update(GENERAL_CUSTOMER_UNIT_TABLE)
            .where(GENERAL_CUSTOMER_UNIT_TABLE.c.id == unit_id)
            .values(**payload)
            .returning(GENERAL_CUSTOMER_UNIT_TABLE)
        )
        with self.engine.begin() as connection:
            current_shop_id = connection.execute(
                select(GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id)
                .where(GENERAL_CUSTOMER_UNIT_TABLE.c.id == unit_id)
            ).scalar_one_or_none()
            if current_shop_id is None:
                return None
            shop_statuses = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.is_active)
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id.in_([current_shop_id, payload["shop_id"]]))
                .order_by(GENERAL_CUSTOMER_SHOP_TABLE.c.id).with_for_update()
            ).scalars().all()
            if not all(shop_statuses):
                raise ValueError("所属店铺已停用，请先启用店铺后再编辑单位")
            row = connection.execute(statement).mappings().first()
            if row is None:
                return None
            shop = connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name, GENERAL_CUSTOMER_SHOP_TABLE.c.shop_name, GENERAL_CUSTOMER_SHOP_TABLE.c.is_active.label("shop_is_active"))
                .where(GENERAL_CUSTOMER_SHOP_TABLE.c.id == payload["shop_id"])
            ).mappings().one()
        item = dict(row)
        item.update(shop)
        return item

    def delete_general_customer_unit(self, unit_id: int) -> bool:
        statement = delete(GENERAL_CUSTOMER_UNIT_TABLE).where(GENERAL_CUSTOMER_UNIT_TABLE.c.id == unit_id)
        with self.engine.begin() as connection:
            connection.execute(
                select(GENERAL_CUSTOMER_SHOP_TABLE.c.id)
                .join(GENERAL_CUSTOMER_UNIT_TABLE, GENERAL_CUSTOMER_UNIT_TABLE.c.shop_id == GENERAL_CUSTOMER_SHOP_TABLE.c.id)
                .where(GENERAL_CUSTOMER_UNIT_TABLE.c.id == unit_id)
                .with_for_update(of=GENERAL_CUSTOMER_SHOP_TABLE)
            ).all()
            unit = connection.execute(
                select(GENERAL_CUSTOMER_UNIT_TABLE.c.unit_name)
                .where(GENERAL_CUSTOMER_UNIT_TABLE.c.id == unit_id).with_for_update()
            ).first()
            if unit is not None and connection.execute(
                select(INVENTORY_TABLE.c.id)
                .where(func.trim(INVENTORY_TABLE.c.supplier) == str(unit[0]).strip()).limit(1)
            ).first() is not None:
                raise ValueError("该单位已有历史业务，不能删除；请停用所属店铺以保留查账入口")
            result = connection.execute(statement)
        return result.rowcount > 0

    # ── Inventory Account Subjects ─────────────────────────────────

    def list_account_subjects(self) -> list[dict[str, object]]:
        statement = select(INVENTORY_ACCOUNT_SUBJECT_TABLE).order_by(
            case((INVENTORY_ACCOUNT_SUBJECT_TABLE.c.category == "收入类", 0), else_=1),
            INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id,
            INVENTORY_ACCOUNT_SUBJECT_TABLE.c.name,
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_account_subject(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {
            "code": str(data.get("code") or "").strip() or None,
            "category": str(data.get("category") or "收入类").strip() or "收入类",
            "name": str(data.get("name") or "").strip(),
        }
        if payload["category"] not in ACCOUNT_SUBJECT_CATEGORIES:
            raise ValueError("科目分类无效")
        statement = insert(INVENTORY_ACCOUNT_SUBJECT_TABLE).values(**payload).returning(INVENTORY_ACCOUNT_SUBJECT_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def get_account_subject(self, subject_id: int) -> dict[str, object] | None:
        statement = select(INVENTORY_ACCOUNT_SUBJECT_TABLE).where(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id == subject_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def update_account_subject(
        self,
        subject_id: int,
        data: Mapping[str, object],
    ) -> tuple[dict[str, object] | None, int]:
        current_name = str(data.get("name") or "").strip()
        requested_category = str(data.get("category") or "").strip()
        with self.engine.begin() as connection:
            before = connection.execute(
                select(INVENTORY_ACCOUNT_SUBJECT_TABLE)
                .where(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id == subject_id)
                .with_for_update()
            ).mappings().first()
            if before is None:
                return None, 0
            current_category = requested_category or str(before.get("category") or "收入类").strip() or "收入类"
            if current_category not in ACCOUNT_SUBJECT_CATEGORIES:
                raise ValueError("科目分类无效")

            row = connection.execute(
                update(INVENTORY_ACCOUNT_SUBJECT_TABLE)
                .where(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id == subject_id)
                .values(name=current_name, category=current_category)
                .returning(INVENTORY_ACCOUNT_SUBJECT_TABLE)
            ).mappings().one()

            previous_name = str(before.get("name") or "").strip()
            synced_detail_count = 0
            if previous_name and current_name and previous_name != current_name:
                synced_detail_count = self._rename_account_subject_references(
                    connection,
                    previous_name=previous_name,
                    current_name=current_name,
                )
        return dict(row), synced_detail_count

    @staticmethod
    def _rename_account_subject_references(
        connection,
        *,
        previous_name: str,
        current_name: str,
    ) -> int:
        accounting_document_ids = select(INVENTORY_TABLE.c.id).where(
            INVENTORY_TABLE.c.document_type.in_(ACCOUNTING_DOCUMENT_TYPES),
        )
        result = connection.execute(
            update(INVENTORY_DETAIL_TABLE)
            .where(
                INVENTORY_DETAIL_TABLE.c.document_id.in_(accounting_document_ids),
                func.btrim(INVENTORY_DETAIL_TABLE.c.product_name) == previous_name,
            )
            .values(
                product_name=current_name,
                updated_at=func.date_trunc("minute", func.now()),
            )
        )
        return result.rowcount or 0

    def delete_account_subject(self, subject_id: int) -> bool:
        statement = delete(INVENTORY_ACCOUNT_SUBJECT_TABLE).where(INVENTORY_ACCOUNT_SUBJECT_TABLE.c.id == subject_id)
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        return result.rowcount > 0

    # ── Purchase Order Requirements ────────────────────────────────

    def list_purchase_order_requirement_templates(self) -> list[dict[str, object]]:
        statement = select(PURCHASE_ORDER_REQUIREMENT_TABLE).order_by(PURCHASE_ORDER_REQUIREMENT_TABLE.c.brand)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def get_purchase_order_requirement_template_map(self) -> dict[str, str]:
        rows = self.list_purchase_order_requirement_templates()
        return {
            str(row.get("brand") or "").strip().lower(): str(row.get("content") or "")
            for row in rows
            if str(row.get("brand") or "").strip()
        }

    def upsert_purchase_order_requirement_template(self, brand: str, content: str) -> dict[str, object]:
        normalized_brand = str(brand or "").strip().lower()
        payload = {
            "brand": normalized_brand,
            "content": str(content or ""),
        }
        insert_statement = pg_insert(PURCHASE_ORDER_REQUIREMENT_TABLE).values(**payload)
        statement = insert_statement.on_conflict_do_update(
            index_elements=[PURCHASE_ORDER_REQUIREMENT_TABLE.c.brand],
            set_={
                "content": insert_statement.excluded.content,
                "updated_at": func.date_trunc('minute', func.now()),
            },
        ).returning(PURCHASE_ORDER_REQUIREMENT_TABLE)
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def list_purchase_print_templates(self, user_id: int) -> list[dict[str, object]]:
        user_id = 0
        statement = (
            select(PURCHASE_PRINT_TEMPLATE_TABLE)
            .where(PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id)
            .order_by(
                PURCHASE_PRINT_TEMPLATE_TABLE.c.is_default.desc(),
                PURCHASE_PRINT_TEMPLATE_TABLE.c.updated_at.desc(),
                PURCHASE_PRINT_TEMPLATE_TABLE.c.id,
            )
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def get_default_purchase_print_template(self, user_id: int) -> dict[str, object] | None:
        user_id = 0
        statement = select(PURCHASE_PRINT_TEMPLATE_TABLE).where(
            PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id,
            PURCHASE_PRINT_TEMPLATE_TABLE.c.is_default.is_(True),
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        if row is not None:
            return dict(row)
        legacy = self.get_purchase_print_template(user_id)
        if legacy is not None:
            return legacy
        templates = self.list_purchase_print_templates(user_id)
        return templates[0] if templates else None

    def get_purchase_print_template_by_key(self, user_id: int, template_key: str) -> dict[str, object] | None:
        return self.get_purchase_print_template(user_id, template_key)

    def get_purchase_print_template(self, user_id: int, template_key: str = "shoe_box_label") -> dict[str, object] | None:
        user_id = 0
        statement = select(PURCHASE_PRINT_TEMPLATE_TABLE).where(
            PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id,
            PURCHASE_PRINT_TEMPLATE_TABLE.c.template_key == template_key,
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def upsert_purchase_print_template(
        self,
        user_id: int,
        config: Mapping[str, object],
        template_key: str = "shoe_box_label",
        template_name: str = "默认模板",
        is_default: bool | None = None,
    ) -> dict[str, object]:
        user_id = 0
        if is_default is None:
            is_default = template_key == "shoe_box_label"
        insert_statement = pg_insert(PURCHASE_PRINT_TEMPLATE_TABLE).values(
            user_id=user_id,
            template_key=template_key,
            template_name=template_name,
            is_default=is_default,
            config=dict(config),
        )
        statement = insert_statement.on_conflict_do_update(
            index_elements=[
                PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id,
                PURCHASE_PRINT_TEMPLATE_TABLE.c.template_key,
            ],
            set_={
                "config": insert_statement.excluded.config,
                "template_name": insert_statement.excluded.template_name,
                "is_default": insert_statement.excluded.is_default,
                "updated_at": func.date_trunc("minute", func.now()),
            },
        ).returning(PURCHASE_PRINT_TEMPLATE_TABLE)
        with self.engine.begin() as connection:
            if is_default:
                connection.execute(
                    update(PURCHASE_PRINT_TEMPLATE_TABLE)
                    .where(PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id)
                    .values(is_default=False)
                )
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def set_default_purchase_print_template(self, user_id: int, template_key: str) -> dict[str, object] | None:
        user_id = 0
        with self.engine.begin() as connection:
            target = connection.execute(
                select(PURCHASE_PRINT_TEMPLATE_TABLE).where(
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id,
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.template_key == template_key,
                )
            ).mappings().first()
            if target is None:
                return None
            connection.execute(
                update(PURCHASE_PRINT_TEMPLATE_TABLE)
                .where(PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id)
                .values(is_default=False)
            )
            row = connection.execute(
                update(PURCHASE_PRINT_TEMPLATE_TABLE)
                .where(PURCHASE_PRINT_TEMPLATE_TABLE.c.id == target["id"])
                .values(is_default=True, updated_at=func.date_trunc("minute", func.now()))
                .returning(PURCHASE_PRINT_TEMPLATE_TABLE)
            ).mappings().one()
        return dict(row)

    def rename_purchase_print_template(self, user_id: int, template_key: str, template_name: str) -> dict[str, object] | None:
        user_id = 0
        with self.engine.begin() as connection:
            row = connection.execute(
                update(PURCHASE_PRINT_TEMPLATE_TABLE)
                .where(
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id,
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.template_key == template_key,
                )
                .values(
                    template_name=template_name,
                    updated_at=func.date_trunc("minute", func.now()),
                )
                .returning(PURCHASE_PRINT_TEMPLATE_TABLE)
            ).mappings().first()
        return None if row is None else dict(row)

    def delete_purchase_print_template(self, user_id: int, template_key: str = "shoe_box_label") -> bool:
        user_id = 0
        with self.engine.begin() as connection:
            target = connection.execute(
                select(PURCHASE_PRINT_TEMPLATE_TABLE).where(
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id,
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.template_key == template_key,
                )
            ).mappings().first()
            if target is None:
                return False
            result = connection.execute(
                delete(PURCHASE_PRINT_TEMPLATE_TABLE).where(
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id,
                    PURCHASE_PRINT_TEMPLATE_TABLE.c.template_key == template_key,
                )
            )
            if target["is_default"]:
                replacement = connection.execute(
                    select(PURCHASE_PRINT_TEMPLATE_TABLE.c.id)
                    .where(PURCHASE_PRINT_TEMPLATE_TABLE.c.user_id == user_id)
                    .order_by(
                        PURCHASE_PRINT_TEMPLATE_TABLE.c.updated_at.desc(),
                        PURCHASE_PRINT_TEMPLATE_TABLE.c.id.desc(),
                    )
                    .limit(1)
                ).scalar()
                if replacement is not None:
                    connection.execute(
                        update(PURCHASE_PRINT_TEMPLATE_TABLE)
                        .where(PURCHASE_PRINT_TEMPLATE_TABLE.c.id == replacement)
                        .values(is_default=True)
                    )
        return bool(result.rowcount)

    # ── Warehouses ─────────────────────────────────────────────────

    def list_warehouses(self) -> list[dict[str, object]]:
        statement = (
            select(WAREHOUSE_TABLE)
            .outerjoin(WAREHOUSE_BRAND_TABLE, WAREHOUSE_BRAND_TABLE.c.name == WAREHOUSE_TABLE.c.brand)
            .order_by(WAREHOUSE_BRAND_TABLE.c.sort_order, WAREHOUSE_TABLE.c.sort_order, WAREHOUSE_TABLE.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def list_warehouse_brands(self) -> list[dict[str, object]]:
        warehouse_count = (
            select(
                WAREHOUSE_TABLE.c.brand.label("brand_name"),
                func.count().label("warehouse_count"),
            )
            .group_by(WAREHOUSE_TABLE.c.brand)
            .subquery()
        )
        statement = (
            select(
                WAREHOUSE_BRAND_TABLE.c.id,
                WAREHOUSE_BRAND_TABLE.c.name,
                WAREHOUSE_BRAND_TABLE.c.sort_order,
                WAREHOUSE_BRAND_TABLE.c.created_at,
                WAREHOUSE_BRAND_TABLE.c.updated_at,
                func.coalesce(warehouse_count.c.warehouse_count, 0).label("warehouse_count"),
            )
            .outerjoin(warehouse_count, warehouse_count.c.brand_name == WAREHOUSE_BRAND_TABLE.c.name)
            .order_by(WAREHOUSE_BRAND_TABLE.c.sort_order, WAREHOUSE_BRAND_TABLE.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def create_warehouse_brand(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = {"name": str(data.get("name") or "").strip()}
        with self.engine.begin() as connection:
            payload["sort_order"] = self._next_sort_order(connection, WAREHOUSE_BRAND_TABLE)
            statement = (
                insert(WAREHOUSE_BRAND_TABLE)
                .values(**payload)
                .returning(
                    WAREHOUSE_BRAND_TABLE.c.id,
                    WAREHOUSE_BRAND_TABLE.c.name,
                    WAREHOUSE_BRAND_TABLE.c.sort_order,
                    WAREHOUSE_BRAND_TABLE.c.created_at,
                    WAREHOUSE_BRAND_TABLE.c.updated_at,
                )
            )
            row = connection.execute(statement).mappings().one()
        record = dict(row)
        record["warehouse_count"] = 0
        return record

    def get_warehouse_brand(self, brand_id: int) -> dict[str, object] | None:
        warehouse_count = (
            select(func.count())
            .select_from(WAREHOUSE_TABLE)
            .where(WAREHOUSE_TABLE.c.brand == WAREHOUSE_BRAND_TABLE.c.name)
            .scalar_subquery()
        )
        statement = select(
            WAREHOUSE_BRAND_TABLE.c.id,
            WAREHOUSE_BRAND_TABLE.c.name,
            WAREHOUSE_BRAND_TABLE.c.sort_order,
            WAREHOUSE_BRAND_TABLE.c.created_at,
            WAREHOUSE_BRAND_TABLE.c.updated_at,
            warehouse_count.label("warehouse_count"),
        ).where(WAREHOUSE_BRAND_TABLE.c.id == brand_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_warehouse_brand_by_name(self, name: str) -> dict[str, object] | None:
        statement = select(WAREHOUSE_BRAND_TABLE).where(WAREHOUSE_BRAND_TABLE.c.name == name)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def reorder_warehouse_brands(self, ordered_ids: list[int]) -> bool:
        return self._replace_sort_order(WAREHOUSE_BRAND_TABLE, ordered_ids)

    def update_warehouse_brand(self, brand_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = {"name": str(data.get("name") or "").strip()}
        with self.engine.begin() as connection:
            previous = connection.execute(
                select(WAREHOUSE_BRAND_TABLE.c.name).where(WAREHOUSE_BRAND_TABLE.c.id == brand_id)
            ).mappings().first()
            if previous is None:
                return None
            row = connection.execute(
                update(WAREHOUSE_BRAND_TABLE)
                .where(WAREHOUSE_BRAND_TABLE.c.id == brand_id)
                .values(**payload)
                .returning(
                    WAREHOUSE_BRAND_TABLE.c.id,
                    WAREHOUSE_BRAND_TABLE.c.name,
                    WAREHOUSE_BRAND_TABLE.c.created_at,
                    WAREHOUSE_BRAND_TABLE.c.updated_at,
                )
            ).mappings().first()
            if row is None:
                return None
            old_name = str(previous["name"] or "")
            if old_name != payload["name"]:
                connection.execute(
                    update(WAREHOUSE_TABLE)
                    .where(WAREHOUSE_TABLE.c.brand == old_name)
                    .values(brand=payload["name"])
                )
            warehouse_count = connection.execute(
                select(func.count()).select_from(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.brand == payload["name"])
            ).scalar_one()
        record = dict(row)
        record["warehouse_count"] = warehouse_count
        return record

    def delete_warehouse_brand(self, brand_id: int) -> str | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(WAREHOUSE_BRAND_TABLE.c.name).where(WAREHOUSE_BRAND_TABLE.c.id == brand_id)
            ).first()
            if row is None:
                return "not_found"
            brand_name = str(row[0] or "")
            has_warehouses = connection.execute(
                select(WAREHOUSE_TABLE.c.id).where(WAREHOUSE_TABLE.c.brand == brand_name).limit(1)
            ).first()
            if has_warehouses is not None:
                return "in_use"
            result = connection.execute(delete(WAREHOUSE_BRAND_TABLE).where(WAREHOUSE_BRAND_TABLE.c.id == brand_id))
        return None if result.rowcount > 0 else "not_found"

    def create_warehouse(self, data: Mapping[str, object]) -> dict[str, object]:
        payload = dict(data)
        payload["brand"] = str(payload.get("brand") or "").strip()
        if not payload["brand"]:
            raise ValueError("仓库品牌不能为空")
        with self.engine.begin() as connection:
            payload["sort_order"] = self._next_sort_order(
                connection,
                WAREHOUSE_TABLE,
                WAREHOUSE_TABLE.c.brand == payload["brand"],
            )
            statement = insert(WAREHOUSE_TABLE).values(**payload).returning(WAREHOUSE_TABLE)
            row = connection.execute(statement).mappings().one()
        return dict(row)

    def reorder_warehouses(self, brand: str, ordered_ids: list[int]) -> bool:
        return self._replace_sort_order(
            WAREHOUSE_TABLE,
            ordered_ids,
            WAREHOUSE_TABLE.c.brand == brand,
        )

    def update_warehouse(self, warehouse_id: int, data: Mapping[str, object]) -> dict[str, object] | None:
        payload = dict(data)
        payload.pop("id", None)
        with self.engine.begin() as connection:
            before = connection.execute(
                select(WAREHOUSE_TABLE.c.name).where(WAREHOUSE_TABLE.c.id == warehouse_id)
            ).scalar_one_or_none()
            if before is None:
                return None
            previous_name = str(before).strip()
            next_name = str(payload.get("name") or previous_name).strip()
            if next_name and next_name != previous_name:
                connection.execute(
                    update(INVENTORY_TABLE)
                    .where(INVENTORY_TABLE.c.warehouse == previous_name)
                    .values(warehouse=next_name)
                )
                connection.execute(
                    update(INVENTORY_TABLE)
                    .where(
                        INVENTORY_TABLE.c.document_type == "同价调拨单",
                        INVENTORY_TABLE.c.supplier == previous_name,
                    )
                    .values(supplier=next_name)
                )
            statement = update(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.id == warehouse_id).values(**payload).returning(WAREHOUSE_TABLE)
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def get_warehouse(self, warehouse_id: int) -> dict[str, object] | None:
        statement = select(WAREHOUSE_TABLE).where(WAREHOUSE_TABLE.c.id == warehouse_id)
        with self.engine.connect() as connection:
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

    # ── Warehouse inventory ───────────────────────────────────────

    @staticmethod
    def _warehouse_inventory_expressions(warehouse_name: str, *, quantity=None):
        """Return inbound, outbound and scope expressions for one warehouse."""
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        if quantity is None:
            quantity = func.coalesce(detail.c.quantity, 0)
        inbound_types = WAREHOUSE_INBOUND_TYPES
        outbound_types = WAREHOUSE_OUTBOUND_TYPES

        inbound = case(
            (
                or_(
                    and_(record.c.document_type.in_(inbound_types), record.c.warehouse == warehouse_name),
                    and_(record.c.document_type == "同价调拨单", record.c.warehouse == warehouse_name),
                ),
                quantity,
            ),
            else_=0,
        )
        outbound = case(
            (
                or_(
                    and_(record.c.document_type.in_(outbound_types), record.c.warehouse == warehouse_name),
                    and_(record.c.document_type == "同价调拨单", record.c.supplier == warehouse_name),
                ),
                quantity,
            ),
            else_=0,
        )
        affected = or_(
            and_(record.c.document_type.in_(inbound_types + outbound_types), record.c.warehouse == warehouse_name),
            and_(
                record.c.document_type == "同价调拨单",
                or_(record.c.warehouse == warehouse_name, record.c.supplier == warehouse_name),
            ),
        )
        return inbound, outbound, affected

    def list_warehouse_inventory_summary(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> list[dict[str, object]]:
        cache = getattr(self, "_warehouse_inventory_cache", None)
        version = self._warehouse_inventory_version() if cache is not None else None
        if version is not None:
            def load_summary():
                items = self._query_warehouse_inventory_summary(date_start=date_start, date_end=date_end)
                if self._warehouse_inventory_version() != version:
                    return None
                return InventoryGroups.from_result({"items": items, "total": len(items), "totals": {}})

            groups = cache.get_or_load(("summary", version, date_start, date_end), load_summary)
            if groups is not None:
                return groups.page(1, MAX_GROUPS, False)["items"]
        return self._query_warehouse_inventory_summary(date_start=date_start, date_end=date_end)

    def _warehouse_inventory_version(self, connection=None) -> str | None:
        if self.engine.dialect.name != "postgresql":
            return None
        if connection is None:
            with self.engine.connect() as connection:
                return self._warehouse_inventory_version(connection)
        capabilities = connection.execute(CAPABILITIES_SQL).mappings().one()
        self._warehouse_stock_index_ready = capabilities["stock_index_ready"]
        return connection.execute(VERSION_SQL).scalar_one() if capabilities["revisions_ready"] else None

    def _query_warehouse_inventory_summary(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> list[dict[str, object]]:
        """Aggregate all warehouses with one reusable quantity total per document."""
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        start_date = parse_date(date_start) if date_start else None
        end_date = parse_date(date_end) if date_end else None
        conditions = [
            record.c.deleted_at.is_(None),
            record.c.document_type.in_((*WAREHOUSE_INBOUND_TYPES, *WAREHOUSE_OUTBOUND_TYPES, "同价调拨单")),
            self._record_completion_condition("completed"),
        ]
        if end_date:
            conditions.append(or_(
                record.c.date_value <= end_date,
                and_(record.c.date_value.is_(None), record.c.date <= date_end),
            ))

        if start_date:
            before_period = or_(
                record.c.date_value < start_date,
                and_(record.c.date_value.is_(None), record.c.date < date_start),
            )
            in_period = or_(
                record.c.date_value >= start_date,
                and_(record.c.date_value.is_(None), record.c.date >= date_start),
            )
        else:
            before_period = literal(False)
            in_period = literal(True)

        # Check completion once per document before joining millions of details.
        # The PostgreSQL fence also prevents a detail-first plan with repeated
        # document lookups and completion subqueries for each detail row.
        documents = (
            select(
                record.c.id,
                record.c.warehouse,
                case((record.c.document_type == "同价调拨单", record.c.supplier)).label("outgoing_warehouse"),
                case((record.c.document_type.in_((*WAREHOUSE_INBOUND_TYPES, "同价调拨单")), 1), else_=-1).label("direction"),
                before_period.label("before_period"),
                or_(before_period, in_period).label("through_period"),
            )
            .where(*conditions)
            .cte("warehouse_summary_documents")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )
        # Aggregate via the covering document index before joining the wider
        # document data; carrying every detail into that join is much costlier.
        quantities = (
            select(
                detail.c.document_id,
                func.sum(func.coalesce(detail.c.quantity, 0)).label("quantity"),
            )
            .group_by(detail.c.document_id)
            .subquery("warehouse_document_quantities")
        )
        change = quantities.c.quantity * documents.c.direction
        # Compact to warehouse pairs first, then reuse these small totals for
        # both transfer ends. Never substitute the document's total_count.
        balances = (
            select(
                documents.c.warehouse,
                documents.c.outgoing_warehouse,
                func.sum(case((documents.c.before_period, change), else_=0)).label("beginning_qty"),
                # Match detail totals even for legacy records with no date.
                func.sum(case((documents.c.through_period, change), else_=0)).label("ending_qty"),
            )
            .select_from(documents.join(quantities, quantities.c.document_id == documents.c.id))
            .group_by(documents.c.warehouse, documents.c.outgoing_warehouse)
            .cte("warehouse_summary_balances")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )

        warehouse_movements = union_all(
            select(
                balances.c.warehouse.label("warehouse_name"),
                balances.c.beginning_qty,
                balances.c.ending_qty,
            ),
            select(
                balances.c.outgoing_warehouse.label("warehouse_name"),
                -balances.c.beginning_qty,
                -balances.c.ending_qty,
            ).where(balances.c.outgoing_warehouse.is_not(None)),
        ).subquery()
        totals = (
            select(
                warehouse_movements.c.warehouse_name,
                func.sum(warehouse_movements.c.beginning_qty).label("beginning_qty"),
                func.sum(warehouse_movements.c.ending_qty).label("ending_qty"),
            )
            .group_by(warehouse_movements.c.warehouse_name)
            .subquery()
        )
        statement = (
            select(
                WAREHOUSE_TABLE.c.id.label("warehouse_id"),
                func.coalesce(totals.c.beginning_qty, 0).label("beginning_qty"),
                func.coalesce(totals.c.ending_qty, 0).label("ending_qty"),
            )
            .select_from(WAREHOUSE_TABLE.outerjoin(totals, totals.c.warehouse_name == WAREHOUSE_TABLE.c.name))
            .order_by(WAREHOUSE_TABLE.c.id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [{
            "warehouse_id": row["warehouse_id"],
            "beginning_qty": self._format_decimal(Decimal(str(row["beginning_qty"]))),
            "ending_qty": self._format_decimal(Decimal(str(row["ending_qty"]))),
        } for row in rows]

    def get_warehouse_inventory(
        self,
        *,
        warehouse_name: str,
        date_start: str | None = None,
        date_end: str | None = None,
        product_code: str | None = None,
        ending_nonzero: bool = False,
        display_mode: str = "goods",
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        from storage.warehouse_inventory_barcodes import enrich_stock_barcodes
        filters = dict(warehouse_name=warehouse_name, date_start=date_start, date_end=date_end, product_code=product_code)
        if display_mode == "barcode":
            filters["display_mode"] = "barcode"
        cache = getattr(self, "_warehouse_inventory_cache", None)
        version = self._warehouse_inventory_version() if cache is not None else None
        if version is not None:
            def load_groups():
                if display_mode == "barcode":
                    groups = self._query_warehouse_inventory(**filters, ending_nonzero=False, page=1,
                        page_size=MAX_BARCODE_GROUPS + 1, _cache_groups=True)
                else:
                    result = self._query_warehouse_inventory(**filters, ending_nonzero=False, page=1, page_size=MAX_GROUPS + 1)
                    groups = InventoryGroups.from_result(result)
                # Do not retain a result if source data committed while the
                # aggregation was in progress. Fall back to a fresh SQL query.
                if self._warehouse_inventory_version() != version:
                    return None
                return groups

            key = ("detail", version, warehouse_name, date_start, date_end, product_code.strip() if product_code else None, display_mode)
            groups = cache.get_or_load(key, load_groups)
            if groups is not None:
                result = groups.page(page, page_size, ending_nonzero)
                return enrich_stock_barcodes(self, result) if display_mode == "barcode" else result
        result = self._query_warehouse_inventory(**filters, ending_nonzero=ending_nonzero, page=page, page_size=page_size)
        return enrich_stock_barcodes(self, result) if display_mode == "barcode" else result

    def _query_warehouse_inventory(
        self,
        *,
        warehouse_name: str,
        date_start: str | None = None,
        date_end: str | None = None,
        product_code: str | None = None,
        ending_nonzero: bool = False,
        display_mode: str = "goods",
        page: int,
        page_size: int,
        _cache_groups: bool = False,
    ) -> dict[str, object] | CompressedInventoryGroups | None:
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        inbound_direction, outbound_direction, affected = self._warehouse_inventory_expressions(
            warehouse_name, quantity=literal(1),
        )
        start_date = parse_date(date_start) if date_start else None
        end_date = parse_date(date_end) if date_end else None

        conditions = [record.c.deleted_at.is_(None), self._record_completion_condition("completed"), affected]
        if end_date:
            conditions.append(or_(
                record.c.date_value <= end_date,
                and_(record.c.date_value.is_(None), record.c.date <= date_end),
            ))
        elif date_end:
            conditions.append(record.c.date <= date_end)
        if start_date:
            before_period = or_(
                record.c.date_value < start_date,
                and_(record.c.date_value.is_(None), record.c.date < date_start),
            )
            in_period = or_(
                record.c.date_value >= start_date,
                and_(record.c.date_value.is_(None), record.c.date >= date_start),
            )
        elif date_start:
            before_period = record.c.date < date_start
            in_period = record.c.date >= date_start
        else:
            before_period = False
            in_period = True

        # Resolve document-wide rules and period/direction flags once before
        # joining details; a product filter must not hide missing-price lines
        # when checking whether the entire document is completed.
        documents = (
            select(
                record.c.id,
                case((before_period, inbound_direction - outbound_direction), else_=0).label("beginning_direction"),
                case((in_period, inbound_direction), else_=0).label("inbound_direction"),
                case((in_period, outbound_direction), else_=0).label("outbound_direction"),
            )
            .where(*conditions)
            .cte("warehouse_inventory_documents")
        )
        # Full inventory benefits from checking each document once. A product
        # search must allow PostgreSQL to start with its selective detail index.
        if not product_code:
            documents = documents.prefix_with("MATERIALIZED", dialect="postgresql")
        if not product_code and (
            getattr(self, "_warehouse_stock_index_ready", False)
            or (display_mode == "barcode" and self.engine.dialect.name == "postgresql")
        ):
            # Goods use the covering index; barcode mode additionally needs
            # recorded sizes from the heap. In both cases avoid scanning other
            # warehouses. OFFSET 0 retains the per-document index lookup.
            detail = (
                select(detail.c.product_code, detail.c.product_name, detail.c.color_name,
                       detail.c.color_spec, detail.c.quantity,
                       *([detail.c.id, detail.c.product_identity_id, detail.c.size_quantities] if display_mode == "barcode" else []))
                .where(detail.c.document_id == documents.c.id)
                .correlate(documents)
                .offset(0)
                .lateral("warehouse_stock_lines")
            )
            joined = documents.join(detail, true())
        else:
            joined = documents.join(detail, detail.c.document_id == documents.c.id)
        if display_mode == "barcode":
            from storage.warehouse_inventory_barcodes import expand_stock_sizes
            size_source = select(
                detail.c.id, detail.c.product_identity_id, detail.c.product_code, detail.c.product_name,
                detail.c.color_name, detail.c.color_spec, detail.c.size_quantities,
                func.coalesce(detail.c.quantity, 0).label("quantity"),
                documents.c.beginning_direction, documents.c.inbound_direction, documents.c.outbound_direction,
            ).select_from(joined).where(detail.c.product_code.ilike(f"%{product_code.strip()}%") if product_code else true())
            detail = expand_stock_sizes(size_source, self.engine.dialect.name, aggregate=True)
            joined = detail
            documents = detail
        extra_groups = [detail.c.product_identity_id, detail.c.inventory_size_key, detail.c.unallocated] if display_mode == "barcode" else []
        quantity = func.coalesce(detail.c.quantity, 0)
        # Most historical groups have no movements this period; FILTER avoids
        # creating numeric aggregate states just to add zero for every old row.
        beginning_qty = func.coalesce(func.sum(quantity * documents.c.beginning_direction).filter(
            documents.c.beginning_direction != 0,
        ), 0).label("beginning_qty")
        inbound_quantity = quantity * documents.c.inbound_direction if display_mode == "barcode" else quantity
        outbound_quantity = quantity * documents.c.outbound_direction if display_mode == "barcode" else quantity
        inbound_qty = func.coalesce(func.sum(inbound_quantity).filter(documents.c.inbound_direction != 0), 0).label("inbound_qty")
        outbound_qty = func.coalesce(func.sum(outbound_quantity).filter(documents.c.outbound_direction != 0), 0).label("outbound_qty")
        grouped = (
            select(
                detail.c.product_code,
                detail.c.product_name,
                detail.c.color_name,
                detail.c.color_spec,
                *extra_groups,
                *([func.min(detail.c.id).label("id")] if display_mode == "barcode" else []),
                beginning_qty,
                inbound_qty,
                outbound_qty,
            )
            .select_from(joined)
            .where(detail.c.product_code.ilike(f"%{product_code.strip()}%") if product_code else true())
            .group_by(
                detail.c.product_code,
                detail.c.product_name,
                detail.c.color_name,
                detail.c.color_spec,
                *extra_groups,
            )
            .cte("warehouse_inventory_grouped")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )
        ending_qty = (grouped.c.beginning_qty + grouped.c.inbound_qty - grouped.c.outbound_qty).label("ending_qty")
        item_count = func.count(case((ending_qty != 0, 1))) if ending_nonzero else func.count()
        totals = select(
            item_count.label("total"),
            func.coalesce(func.sum(grouped.c.beginning_qty), 0).label("total_beginning_qty"),
            func.coalesce(func.sum(grouped.c.inbound_qty), 0).label("total_inbound_qty"),
            func.coalesce(func.sum(grouped.c.outbound_qty), 0).label("total_outbound_qty"),
            func.coalesce(func.sum(ending_qty), 0).label("total_ending_qty"),
        ).cte("warehouse_inventory_totals")
        sort_columns = [grouped.c.product_code, grouped.c.color_name, grouped.c.color_spec, grouped.c.product_name]
        if display_mode == "barcode":
            sort_columns.extend((grouped.c.product_identity_id, grouped.c.unallocated, grouped.c.inventory_size_key))
        if _cache_groups:
            # Stream already aggregated rows into small compressed blocks.
            # Do not build a list of all barcode rows or count/scan the CTE
            # again; the same pass supplies totals and the nonzero index.
            statement = select(grouped, ending_qty).order_by(*sort_columns).limit(MAX_BARCODE_GROUPS + 1)
            fields = ("beginning_qty", "inbound_qty", "outbound_qty", "ending_qty")
            sums = {field: Decimal(0) for field in fields}
            cache_totals = {}
            def stock_rows(cursor):
                for row in cursor.mappings():
                    item = {key: row[key] for key in (
                        "id", "product_identity_id", "product_code", "product_name", "color_name", "color_spec",
                        "inventory_size_key", "unallocated",
                    )}
                    for field in fields:
                        value = Decimal(str(row[field] or 0))
                        sums[field] += value
                        item[field] = self._format_decimal(value)
                    yield item
                cache_totals.update({field: self._format_decimal(value) for field, value in sums.items()})
            with self.engine.connect() as connection:
                with connection.execute(statement.execution_options(yield_per=256)) as cursor:
                    return CompressedInventoryGroups.from_rows(stock_rows(cursor), cache_totals)
        paged = (
            select(grouped, ending_qty, literal(True).label("has_item"))
            .where(ending_qty != 0 if ending_nonzero else true())
            .order_by(*sort_columns)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .cte("warehouse_inventory_page")
        )
        # Filter ending stock before counting/paging, keeping negative balances.
        # Cards retain all movements, including products with zero ending stock.
        # One aggregation and outer join preserve totals even for an empty page.
        statement = (
            select(totals, paged)
            .select_from(totals.outerjoin(paged, true()))
            .order_by(*(paged.c[column.key] for column in sort_columns))
        )

        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        totals = rows[0]
        total = int(totals["total"])

        def format_quantity(value: object) -> str:
            return self._format_decimal(Decimal(str(value or "0")))

        items = [{
            **({key: row[key] for key in ("id", "product_identity_id", "inventory_size_key", "unallocated")} if display_mode == "barcode" else {}),
            "product_code": row.get("product_code"),
            "product_name": row.get("product_name"),
            "color_name": row.get("color_name"),
            "color_spec": row.get("color_spec"),
            "beginning_qty": format_quantity(row.get("beginning_qty")),
            "inbound_qty": format_quantity(row.get("inbound_qty")),
            "outbound_qty": format_quantity(row.get("outbound_qty")),
            "ending_qty": format_quantity(row.get("ending_qty")),
        } for row in rows if row["has_item"]]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "totals": {
                "beginning_qty": format_quantity(totals.get("total_beginning_qty")),
                "inbound_qty": format_quantity(totals.get("total_inbound_qty")),
                "outbound_qty": format_quantity(totals.get("total_outbound_qty")),
                "ending_qty": format_quantity(totals.get("total_ending_qty")),
            },
        }

    def list_warehouse_inventory_movements(
        self,
        *,
        warehouse_name: str,
        date_start: str | None = None,
        date_end: str | None = None,
        product_code: str | None = None,
        product_name: str | None = None,
        color_name: str | None = None,
        color_spec: str | None = None,
        exact_match: bool = False,
        display_mode: str = "goods",
        product_identity_id: int | None = None,
        inventory_size_key: str | None = None,
        unallocated: bool = False,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        joined = detail.join(record, detail.c.document_id == record.c.id)
        inbound, outbound, affected = self._warehouse_inventory_expressions(warehouse_name)
        conditions = [record.c.deleted_at.is_(None), self._record_completion_condition("completed"), affected]
        start_date = parse_date(date_start) if date_start else None
        end_date = parse_date(date_end) if date_end else None
        if start_date:
            before_period = or_(
                record.c.date_value < start_date,
                and_(record.c.date_value.is_(None), record.c.date < date_start),
            )
            in_period = or_(
                record.c.date_value >= start_date,
                and_(record.c.date_value.is_(None), record.c.date >= date_start),
            )
        elif date_start:
            before_period = record.c.date < date_start
            in_period = record.c.date >= date_start
        else:
            before_period = False
            in_period = True
        if end_date:
            conditions.append(or_(
                record.c.date_value <= end_date,
                and_(record.c.date_value.is_(None), record.c.date <= date_end),
            ))
        elif date_end:
            conditions.append(record.c.date <= date_end)
        if exact_match:
            # Match all grouping fields, including NULL and empty values, so a
            # drilldown cannot combine a different product, name or color row.
            conditions.extend((
                detail.c.product_code == product_code,
                detail.c.product_name == product_name,
                detail.c.color_name == color_name,
                detail.c.color_spec == color_spec,
            ))
        else:
            if product_code:
                conditions.append(detail.c.product_code.ilike(f"%{product_code.strip()}%"))
            if product_name is not None:
                conditions.append(detail.c.product_name == product_name)
            if color_name:
                conditions.append(detail.c.color_name == color_name)
            if color_spec:
                conditions.append(detail.c.color_spec == color_spec)

        if display_mode == "barcode":
            from storage.warehouse_inventory_barcodes import expand_stock_sizes
            direction_in, direction_out, _ = self._warehouse_inventory_expressions(warehouse_name, quantity=literal(1))
            expanded = expand_stock_sizes(select(
                detail.c.id, detail.c.product_identity_id, detail.c.product_code, detail.c.product_name,
                detail.c.color_name, detail.c.color_spec, detail.c.size_quantities,
                func.coalesce(detail.c.quantity, 0).label("quantity"),
                record.c.id.label("document_id"), record.c.date, record.c.date_value, record.c.document_type,
                record.c.document_number, record.c.supplier, record.c.warehouse, record.c.summary, record.c.handler,
                direction_in.label("inbound_direction"), direction_out.label("outbound_direction"),
                case((before_period, True), else_=False).label("before_period"),
                case((in_period, True), else_=False).label("in_period"),
            ).select_from(joined).where(*conditions, detail.c.product_identity_id == product_identity_id), self.engine.dialect.name)
            detail = record = expanded
            joined = expanded
            conditions = [expanded.c.inventory_size_key == inventory_size_key, expanded.c.unallocated == unallocated]
            inbound = expanded.c.quantity * expanded.c.inbound_direction
            outbound = expanded.c.quantity * expanded.c.outbound_direction
            before_period, in_period = expanded.c.before_period, expanded.c.in_period
        scoped = (
            select(
                detail.c.id.label("detail_id"),
                (record.c.document_id if display_mode == "barcode" else record.c.id).label("document_id"),
                record.c.date,
                record.c.date_value,
                record.c.document_type,
                record.c.document_number,
                record.c.supplier,
                record.c.warehouse,
                record.c.summary,
                record.c.handler,
                detail.c.product_code,
                detail.c.product_name,
                detail.c.color_name,
                detail.c.color_spec,
                inbound.label("inbound_qty"),
                outbound.label("outbound_qty"),
                (inbound - outbound).label("change_qty"),
                case((before_period, inbound - outbound), else_=0).label("beginning_change_qty"),
                case((in_period, True), else_=False).label("in_period"),
            )
            .select_from(joined)
            .where(and_(*conditions))
            .cte("warehouse_inventory_movements")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )
        beginning_qty = func.coalesce(func.sum(scoped.c.beginning_change_qty), 0)
        inbound_qty = func.coalesce(func.sum(case((scoped.c.in_period, scoped.c.inbound_qty), else_=0)), 0)
        outbound_qty = func.coalesce(func.sum(case((scoped.c.in_period, scoped.c.outbound_qty), else_=0)), 0)
        totals = select(
            func.coalesce(func.sum(case((scoped.c.in_period, 1), else_=0)), 0).label("total"),
            beginning_qty.label("total_beginning_qty"),
            inbound_qty.label("total_inbound_qty"),
            outbound_qty.label("total_outbound_qty"),
            (beginning_qty + inbound_qty - outbound_qty).label("total_ending_qty"),
        ).cte("warehouse_inventory_movement_totals")
        paged = (
            select(scoped, literal(True).label("has_item"))
            .where(scoped.c.in_period)
            .order_by(scoped.c.date_value.nulls_last(), scoped.c.date, scoped.c.document_number, scoped.c.detail_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .cte("warehouse_inventory_movement_page")
        )
        # Cards, count and the page share one database snapshot, even if the
        # source documents change after the summary screen was loaded.
        statement = (
            select(totals, paged)
            .select_from(totals.outerjoin(paged, true()))
            .order_by(paged.c.date_value.nulls_last(), paged.c.date, paged.c.document_number, paged.c.detail_id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        aggregate = rows[0]

        def format_quantity(value: object) -> str:
            return self._format_decimal(Decimal(str(value or "0")))

        return {
            "items": [{
                **{key: row[key] for key in (
                    "detail_id", "document_id", "date", "date_value", "document_type", "document_number",
                    "supplier", "warehouse", "summary", "handler", "product_code", "product_name",
                    "color_name", "color_spec",
                )},
                "inbound_qty": format_quantity(row.get("inbound_qty")),
                "outbound_qty": format_quantity(row.get("outbound_qty")),
                "change_qty": format_quantity(row.get("change_qty")),
            } for row in rows if row["has_item"]],
            "total": int(aggregate["total"]),
            "page": page,
            "page_size": page_size,
            "totals": {
                "beginning_qty": format_quantity(aggregate["total_beginning_qty"]),
                "inbound_qty": format_quantity(aggregate["total_inbound_qty"]),
                "outbound_qty": format_quantity(aggregate["total_outbound_qty"]),
                "ending_qty": format_quantity(aggregate["total_ending_qty"]),
            },
        }

    # ── Inventory Details ───────────────────────────────────────────

    def list_details(self, document_id: int) -> list[dict[str, object]]:
        table = INVENTORY_DETAIL_TABLE
        statement = select(table).where(table.c.document_id == document_id).order_by(table.c.id)
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def list_details_page(
        self,
        document_id: int,
        *,
        page: int,
        page_size: int,
        unit_price_values: list[Decimal | None] | None = None,
    ) -> dict[str, object]:
        table = INVENTORY_DETAIL_TABLE
        normalized_page = max(1, page)
        normalized_page_size = min(max(1, page_size), 500)
        offset = (normalized_page - 1) * normalized_page_size
        conditions = [table.c.document_id == document_id]
        if unit_price_values is not None:
            numeric_values = [value for value in unit_price_values if value is not None]
            value_conditions = []
            if numeric_values:
                value_conditions.append(table.c.unit_price.in_(numeric_values))
            if None in unit_price_values:
                value_conditions.append(table.c.unit_price.is_(None))
            if value_conditions:
                conditions.append(or_(*value_conditions))
            else:
                conditions.append(table.c.id.is_(None))
        statement = (
            select(table)
            .where(*conditions)
            .order_by(table.c.id)
            .limit(normalized_page_size)
            .offset(offset)
        )
        with self.engine.connect() as connection:
            total = int(connection.execute(
                select(func.count()).select_from(table).where(*conditions)
            ).scalar_one())
            items = [dict(row) for row in connection.execute(statement).mappings()]
        return {
            "items": items,
            "total": total,
            "page": normalized_page,
            "page_size": normalized_page_size,
        }

    def list_detail_unit_price_options(
        self,
        document_id: int,
        *,
        search: str | None = None,
        limit: int = 5000,
    ) -> dict[str, object]:
        table = INVENTORY_DETAIL_TABLE
        normalized_limit = min(max(1, limit), 5000)
        conditions = [table.c.document_id == document_id]
        normalized_search = (search or "").strip()
        if normalized_search:
            price_matches = table.c.unit_price.cast(Text).ilike(f"%{normalized_search}%")
            if normalized_search in {"空白", "（空白）", "(空白)"}:
                conditions.append(or_(price_matches, table.c.unit_price.is_(None)))
            else:
                conditions.append(price_matches)

        grouped = (
            select(
                table.c.unit_price.label("value"),
                func.count().label("count"),
            )
            .where(*conditions)
            .group_by(table.c.unit_price)
            .order_by(table.c.unit_price.desc().nulls_first())
        )
        with self.engine.connect() as connection:
            total = int(connection.execute(
                select(func.count()).select_from(grouped.order_by(None).subquery())
            ).scalar_one())
            rows = connection.execute(grouped.limit(normalized_limit + 1)).mappings().all()

        truncated = len(rows) > normalized_limit
        return {
            "items": [
                {
                    "value": None if row["value"] is None else self._format_decimal(Decimal(str(row["value"]))),
                    "count": int(row["count"]),
                }
                for row in rows[:normalized_limit]
            ],
            "total": total,
            "truncated": truncated,
        }

    def get_detail(self, detail_id: int) -> dict[str, object] | None:
        table = INVENTORY_DETAIL_TABLE
        statement = select(table).where(table.c.id == detail_id)
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return None if row is None else dict(row)

    def list_details_for_documents(self, document_ids: list[int]) -> list[dict[str, object]]:
        if not document_ids:
            return []
        table = INVENTORY_DETAIL_TABLE
        identity = PRODUCT_ARCHIVE_IDENTITY_TABLE
        statement = (
            select(table, identity.c.original_sku.label("original_sku"))
            .select_from(table.outerjoin(identity, identity.c.id == table.c.product_identity_id))
            .where(table.c.document_id.in_(document_ids))
            .order_by(table.c.document_id, table.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    @staticmethod
    def purchase_order_product_identity_scope(
        connection,
        product_identity_id: int | None,
    ) -> dict[str, object]:
        return InventoryRepository.document_product_identity_scope(
            connection, product_identity_id, document_type="进货订单",
        )

    @staticmethod
    def document_product_identity_scope(
        connection,
        product_identity_id: int | None,
        *,
        document_type: str | None = None,
    ) -> dict[str, object]:
        if product_identity_id is None:
            return {"details": 0, "documents": 0, "document_ids": []}
        statement = (
            select(INVENTORY_DETAIL_TABLE.c.document_id)
            .select_from(
                INVENTORY_DETAIL_TABLE.join(
                    INVENTORY_TABLE,
                    INVENTORY_TABLE.c.id == INVENTORY_DETAIL_TABLE.c.document_id,
                )
            )
            .where(
                INVENTORY_DETAIL_TABLE.c.product_identity_id == product_identity_id,
            )
        )
        if document_type:
            statement = statement.where(INVENTORY_TABLE.c.document_type == document_type)
        rows = connection.execute(statement).scalars().all()
        document_ids = sorted({int(document_id) for document_id in rows})
        return {
            "details": len(rows),
            "documents": len(document_ids),
            "document_ids": document_ids,
        }

    def list_matching_details_for_documents(
        self,
        document_ids: list[int],
        product_code: str,
    ) -> list[dict[str, object]]:
        normalized_product_code = str(product_code or "").strip()
        if not document_ids or not normalized_product_code:
            return []

        detail = INVENTORY_DETAIL_TABLE
        identity = PRODUCT_ARCHIVE_IDENTITY_TABLE
        stock = JST_STOCK_TABLE
        product_like = f"%{normalized_product_code}%"
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
        statement = (
            select(detail, identity.c.original_sku.label("original_sku"))
            .select_from(detail.outerjoin(identity, identity.c.id == detail.c.product_identity_id))
            .where(
                detail.c.document_id.in_(document_ids),
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
            .order_by(detail.c.document_id, detail.c.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def latest_wholesale_sales_prices(
        self,
        *,
        customer: object,
        product_codes: set[str],
        as_of_date: object | None = None,
        exclude_document_id: object | None = None,
    ) -> dict[str, Decimal]:
        customer_name = str(customer or "").strip()
        normalized_codes = {
            str(product_code or "").strip()
            for product_code in product_codes
            if str(product_code or "").strip()
        }
        if not customer_name or not normalized_codes:
            return {}

        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        conditions = [
            record.c.deleted_at.is_(None),
            record.c.document_type == "批发销售单",
            record.c.supplier == customer_name,
            detail.c.product_code.in_(normalized_codes),
            detail.c.unit_price.is_not(None),
        ]
        parsed_date = parse_date(as_of_date)
        if parsed_date is not None:
            date_text = parsed_date.isoformat()
            conditions.append(or_(
                record.c.date_value <= parsed_date,
                and_(record.c.date_value.is_(None), record.c.date <= date_text),
            ))
        try:
            excluded_id = int(exclude_document_id) if exclude_document_id is not None else None
        except (TypeError, ValueError):
            excluded_id = None
        if excluded_id is not None:
            conditions.append(record.c.id != excluded_id)

        statement = (
            select(
                detail.c.product_code,
                detail.c.unit_price,
            )
            .select_from(detail.join(record, detail.c.document_id == record.c.id))
            .where(and_(*conditions))
            .order_by(
                detail.c.product_code,
                record.c.date_value.desc().nulls_last(),
                record.c.date.desc().nulls_last(),
                record.c.id.desc(),
                detail.c.id.desc(),
            )
        )
        prices: dict[str, Decimal] = {}
        with self.engine.connect() as connection:
            for row in connection.execute(statement).mappings():
                product_code = str(row.get("product_code") or "").strip()
                if product_code and product_code not in prices:
                    prices[product_code] = Decimal(str(row["unit_price"]))
        return prices

    def latest_document_costs(
        self,
        *,
        product_codes: set[str],
        as_of_date: object | None = None,
        exclude_document_id: object | None = None,
    ) -> dict[str, Decimal]:
        codes = {str(code).strip() for code in product_codes if str(code).strip()}
        if not codes:
            return {}
        record = INVENTORY_TABLE
        detail = INVENTORY_DETAIL_TABLE
        conditions = [
            record.c.deleted_at.is_(None),
            record.c.document_type.in_(("进货单", "进货退货单", "进货订单")),
            detail.c.unit_price > 0,
        ]
        parsed_date = parse_date(as_of_date)
        if parsed_date is not None:
            conditions.append(or_(
                record.c.date_value <= parsed_date,
                and_(record.c.date_value.is_(None), record.c.date <= parsed_date.isoformat()),
            ))
        if exclude_document_id is not None:
            conditions.append(record.c.id != int(exclude_document_id))
        statement = (
            select(detail.c.product_code, detail.c.unit_price)
            .select_from(detail.join(record, detail.c.document_id == record.c.id))
            .where(and_(*conditions))
            .order_by(
                detail.c.product_code,
                record.c.date_value.desc().nulls_last(),
                record.c.date.desc().nulls_last(),
                record.c.id.desc(),
                detail.c.id.desc(),
            )
        )
        if self.engine.dialect.name == "postgresql":
            statement = statement.distinct(detail.c.product_code)
        prices: dict[str, Decimal] = {}
        ordered_codes = sorted(codes)
        with self.engine.connect() as connection:
            for offset in range(0, len(ordered_codes), 5000):
                batch = statement.where(detail.c.product_code.in_(ordered_codes[offset:offset + 5000]))
                for row in connection.execute(batch).mappings():
                    code = str(row["product_code"]).strip()
                    if code not in prices:
                        prices[code] = Decimal(str(row["unit_price"]))
        return prices

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

    def overwrite_imported_document(
        self,
        document_id: int,
        *,
        expected_date: object,
        expected_summary: str,
        expected_document_type: str,
        expected_supplier: str,
        expected_warehouse: str,
        record: Mapping[str, object],
        details: list[Mapping[str, object]],
    ) -> dict[str, object] | None:
        record_table = INVENTORY_TABLE
        detail_table = INVENTORY_DETAIL_TABLE
        payload = self._prepare_record(record)
        payload.pop("document_number", None)
        detail_payloads = [
            self._filter_table_payload(detail_table, self._coerce_empty(dict(detail, document_id=document_id)))
            for detail in details
        ]
        with self.engine.begin() as connection:
            self._validate_customer_record(connection, payload)
            existing = connection.execute(
                select(record_table).where(record_table.c.id == document_id, record_table.c.deleted_at.is_(None))
                .with_for_update()
            ).mappings().first()
            if existing is None or (
                parse_date(existing.get("date_value") or existing.get("date")) != parse_date(expected_date)
                or str(existing.get("summary") or "").strip() != expected_summary
                or str(existing.get("document_type") or "").strip() != expected_document_type
                or str(existing.get("supplier") or "").strip() != expected_supplier
                or str(existing.get("warehouse") or "").strip() != expected_warehouse
            ):
                return None
            connection.execute(delete(detail_table).where(detail_table.c.document_id == document_id))
            if detail_payloads:
                connection.execute(insert(detail_table), detail_payloads)
            totals = connection.execute(select(
                func.sum(detail_table.c.quantity), func.sum(detail_table.c.amount)
            ).where(detail_table.c.document_id == document_id)).one()
            if expected_document_type in ACCOUNTING_DOCUMENT_TYPES:
                payload["total_count"] = None
                payload["amount"] = totals[1]
            else:
                payload["total_count"] = self._apply_document_total_sign(expected_document_type, totals[0] or 0)
                payload["amount"] = self._apply_document_total_sign(expected_document_type, totals[1] or 0)
            updated = connection.execute(
                update(record_table).where(record_table.c.id == document_id).values(**payload).returning(record_table)
            ).mappings().one()
        return dict(updated)

    def merge_imported_details(self, document_id: object, rows: list[Mapping[str, object]]) -> dict[str, int]:
        """Merge Excel-imported details without removing existing detail rows.

        The import parser has already grouped rows by product and color.  Matching
        rows refresh the corresponding detail, while rows absent from the workbook
        remain untouched so re-importing a partial workbook cannot remove them.
        """
        table = INVENTORY_DETAIL_TABLE
        payloads = []
        for row in rows:
            payload = self._filter_table_payload(table, self._coerce_empty(row))
            payload["document_id"] = document_id
            payloads.append(payload)

        def match_key(row: Mapping[str, object]) -> tuple[str, str, object]:
            product_code = str(row.get("product_code") or "").strip()
            color_key = str(
                row.get("color_barcode")
                or row.get("color_name")
                or row.get("color_spec")
                or ""
            ).strip()
            return product_code, color_key, row.get("product_identity_id")

        added = 0
        updated = 0
        with self.engine.begin() as connection:
            existing_rows = connection.execute(
                select(table).where(table.c.document_id == document_id).order_by(table.c.id)
            ).mappings()
            existing_by_key: dict[tuple[str, str, object], int] = {}
            existing_by_product: dict[tuple[str, object], list[int]] = {}
            for existing in existing_rows:
                existing_id = int(existing["id"])
                key = match_key(existing)
                existing_by_key.setdefault(key, existing_id)
                if key[0]:
                    existing_by_product.setdefault((key[0], key[2]), []).append(existing_id)

            for payload in payloads:
                key = match_key(payload)
                existing_id = existing_by_key.get(key)
                legacy_key = (key[0], key[1], None)
                if existing_id is None and key[2] is not None:
                    # An old unlinked detail may acquire its archive identity;
                    # details linked to another archive must stay separate.
                    existing_id = existing_by_key.pop(legacy_key, None)
                    if existing_id is not None:
                        existing_by_key[key] = existing_id
                        existing_by_product[(key[0], None)].remove(existing_id)
                        existing_by_product.setdefault((key[0], key[2]), []).append(existing_id)
                # A blank color can safely match only when the document has one
                # existing row for that product code.
                if existing_id is None and not key[1]:
                    candidates = existing_by_product.get((key[0], key[2]), [])
                    if len(candidates) == 1:
                        existing_id = candidates[0]

                if existing_id is None:
                    existing_id = int(
                        connection.execute(
                            insert(table).values(**payload).returning(table.c.id)
                        ).scalar_one()
                    )
                    added += 1
                    existing_by_key.setdefault(key, existing_id)
                    if key[0]:
                        existing_by_product.setdefault((key[0], key[2]), []).append(existing_id)
                    continue

                update_payload = dict(payload)
                update_payload.pop("document_id", None)
                connection.execute(
                    update(table).where(table.c.id == existing_id).values(**update_payload)
                )
                updated += 1

        self.recalculate_totals(document_id)
        return {"added": added, "updated": updated, "total": len(payloads)}

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
                amount = connection.execute(
                    select(func.coalesce(func.sum(detail.c.amount), 0))
                    .where(detail.c.document_id == document_id)
                ).scalar_one()
            else:
                stmt = select(
                    func.coalesce(func.sum(detail.c.quantity), 0),
                    func.coalesce(func.sum(detail.c.amount), 0),
                ).where(detail.c.document_id == document_id)
                total_count, amount = connection.execute(stmt).one()
                total_count = self._apply_document_total_sign(document_type, total_count)
                amount = self._apply_document_total_sign(document_type, amount)
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
        document_type: str | None = None,
        document_numbers: list[str] | None = None,
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
            record.c.deleted_at.is_(None),
            detail.c.product_code.in_(normalized_updates.keys()),
        ]
        if document_type:
            conditions.append(record.c.document_type == document_type)
        else:
            conditions.append(record.c.document_type.in_(PURCHASE_INBOUND_DETAIL_TYPES))
        normalized_document_numbers = list(dict.fromkeys(
            str(document_number or "").strip()
            for document_number in (document_numbers or [])
            if str(document_number or "").strip()
        ))
        if normalized_document_numbers:
            conditions.append(record.c.document_number.in_(normalized_document_numbers))
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

        changed_documents: dict[int, str] = {}
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
                changed_documents[int(row["document_id"])] = str(row.get("document_type") or "")
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

            for document_id, document_type in changed_documents.items():
                totals = connection.execute(
                    select(
                        func.coalesce(func.sum(detail.c.quantity), 0),
                        func.coalesce(func.sum(detail.c.amount), 0),
                    ).where(detail.c.document_id == document_id)
                ).one()
                connection.execute(
                    update(record)
                    .where(record.c.id == document_id)
                    .values(
                        total_count=self._apply_document_total_sign(document_type, totals[0]),
                        amount=self._apply_document_total_sign(document_type, totals[1]),
                    )
                )

        return {
            "updated_details": len(updated_items),
            "updated_documents": len(changed_documents),
            "items": updated_items,
        }

    def list_purchase_cost_document_options(
        self,
        *,
        date_start: str | None,
        date_end: str | None,
        document_type: str | None = None,
    ) -> list[dict[str, object]]:
        record = INVENTORY_TABLE
        conditions = [
            record.c.deleted_at.is_(None),
            record.c.document_number.is_not(None),
            func.btrim(record.c.document_number) != "",
        ]
        if document_type:
            conditions.append(record.c.document_type == document_type)
        else:
            conditions.append(record.c.document_type.in_(PURCHASE_INBOUND_DETAIL_TYPES))
        if date_start:
            parsed = parse_date(date_start)
            conditions.append(record.c.date_value >= parsed if parsed else record.c.date >= date_start)
        if date_end:
            parsed = parse_date(date_end)
            conditions.append(record.c.date_value <= parsed if parsed else record.c.date <= date_end)

        statement = (
            select(
                record.c.document_number,
                record.c.date,
                record.c.document_type,
                record.c.supplier,
                record.c.warehouse,
            )
            .where(and_(*conditions))
            .order_by(record.c.date_value.desc().nulls_last(), record.c.id.desc())
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

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
            INVENTORY_IMPORT_TASK_TABLE.create(connection, checkfirst=True)
            PRODUCT_ARCHIVE_IDENTITY_TABLE.create(connection, checkfirst=True)
            INVENTORY_DETAIL_TABLE.create(connection, checkfirst=True)
            JST_STOCK_TABLE.create(connection, checkfirst=True)
            JST_SIZE_STOCK_SNAPSHOT_TABLE.create(connection, checkfirst=True)
            JST_STOCK_SUMMARY_SNAPSHOT_TABLE.create(connection, checkfirst=True)
            PRODUCT_GOODS_OVERRIDES_TABLE.create(connection, checkfirst=True)
            PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.create(connection, checkfirst=True)
            SIZE_GROUPS_TABLE.create(connection, checkfirst=True)
            SIZE_GROUP_ITEMS_TABLE.create(connection, checkfirst=True)
            for sales_year in HISTORICAL_SALES_YEARS:
                ensure_product_goods_historical_sales_table(connection, sales_year)
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = current_schema()
                              AND table_name = 'product_goods_overrides'
                              AND column_name = 'douyin_hot'
                              AND data_type = 'boolean'
                        ) THEN
                            ALTER TABLE product_goods_overrides
                            ALTER COLUMN douyin_hot TYPE TEXT
                            USING CASE WHEN douyin_hot THEN '是' ELSE NULL END;
                        END IF;
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = current_schema()
                              AND table_name = 'product_goods_overrides'
                              AND column_name = 'clearance'
                              AND data_type = 'boolean'
                        ) THEN
                            ALTER TABLE product_goods_overrides
                            ALTER COLUMN clearance TYPE TEXT
                            USING CASE WHEN clearance THEN '是' ELSE NULL END;
                        END IF;
                    END $$;
                    """
                )
            )
            ensure_columns(connection, "inventory_records", {
                "document_number": "TEXT", "handler": "TEXT", "additional_note": "TEXT", "deleted_at": "TIMESTAMPTZ",
            })
            self._backfill_document_numbers(connection)
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_document_number ON inventory_records (document_number)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_warehouse_date ON inventory_records (warehouse, date_value)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_supplier_date ON inventory_records (supplier, date_value)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_records_deleted_at ON inventory_records (deleted_at)"))
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM inventory_records
                            WHERE deleted_at IS NULL
                              AND NULLIF(BTRIM(document_number), '') IS NOT NULL
                            GROUP BY document_number
                            HAVING COUNT(*) > 1
                        ) THEN
                            RAISE EXCEPTION 'duplicate active inventory document_number exists';
                        END IF;
                    END $$;
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_records_active_document_number
                    ON inventory_records (document_number)
                    WHERE deleted_at IS NULL
                      AND NULLIF(BTRIM(document_number), '') IS NOT NULL
                    """
                )
            )
            ensure_columns(connection, "inventory_details", {
                "color_barcode": "TEXT", "color_name": "TEXT", "size_quantities": "JSON", "remark": "TEXT", "extra_fields": "JSON",
            })
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code ON inventory_details (product_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code ON jst_daily_stock (product_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_inventory_details_product_code_trgm ON inventory_details USING GIN (product_code gin_trgm_ops)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_jst_stock_product_code_trgm ON jst_daily_stock USING GIN (product_code gin_trgm_ops)"))
            INVENTORY_ACCOUNT_SUBJECT_TABLE.create(connection, checkfirst=True)
            subject_columns = ensure_columns(connection, "inventory_account_subjects", {"category": "TEXT"})
            category_default = str(subject_columns.get("category", {}).get("default") or "").strip("()")
            if category_default not in {"'收入类'", "'收入类'::text"}:
                connection.execute(text("ALTER TABLE inventory_account_subjects ALTER COLUMN category SET DEFAULT '收入类'"))
            connection.execute(text("UPDATE inventory_account_subjects SET category = '收入类' WHERE category IS NULL OR BTRIM(category) = ''"))
            ensure_not_null(connection, "inventory_account_subjects", "category")
            self._seed_account_subjects(connection)
            PURCHASE_ORDER_REQUIREMENT_TABLE.create(connection, checkfirst=True)
            PURCHASE_PRINT_TEMPLATE_TABLE.create(connection, checkfirst=True)
            ensure_columns(connection, "purchase_print_templates", {
                "template_name": "TEXT NOT NULL DEFAULT '默认模板'", "is_default": "BOOLEAN NOT NULL DEFAULT FALSE",
            })
            connection.execute(text(
                "UPDATE purchase_print_templates AS current_template "
                "SET is_default = TRUE "
                "WHERE current_template.template_key = 'shoe_box_label' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM purchase_print_templates AS existing_default "
                "  WHERE existing_default.user_id = current_template.user_id "
                "    AND existing_default.is_default = TRUE"
                ")"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_print_templates_user_default "
                "ON purchase_print_templates (user_id) WHERE is_default = TRUE"
            ))
            connection.execute(text(
                "WITH ranked AS ("
                "  SELECT id, ROW_NUMBER() OVER ("
                "    PARTITION BY template_key "
                "    ORDER BY updated_at DESC NULLS LAST, id DESC"
                "  ) AS row_number "
                "  FROM purchase_print_templates"
                ") "
                "UPDATE purchase_print_templates AS template "
                "SET template_key = template.template_key || '_legacy_' || template.id::text "
                "FROM ranked "
                "WHERE template.id = ranked.id AND ranked.row_number > 1"
            ))
            connection.execute(text(
                "WITH selected_default AS ("
                "  SELECT id FROM purchase_print_templates "
                "  ORDER BY is_default DESC, updated_at DESC NULLS LAST, id DESC "
                "  LIMIT 1"
                ") "
                "UPDATE purchase_print_templates AS template "
                "SET is_default = (template.id = selected_default.id) "
                "FROM selected_default"
            ))
            connection.execute(text(
                "UPDATE purchase_print_templates SET user_id = 0 WHERE user_id <> 0"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_print_templates_shared_key "
                "ON purchase_print_templates (template_key)"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_print_templates_shared_default "
                "ON purchase_print_templates (is_default) WHERE is_default = TRUE"
            ))
            SUPPLIER_TABLE.create(connection, checkfirst=True)
            SUPPLIER_BRAND_TABLE.create(connection, checkfirst=True)
            self._ensure_supplier_brand_schema(connection)
            WAREHOUSE_TABLE.create(connection, checkfirst=True)
            WAREHOUSE_BRAND_TABLE.create(connection, checkfirst=True)
            self._ensure_warehouse_schema(connection)
            self._ensure_supplier_schema(connection)
            self._sync_suppliers_from_gj(connection)
            if not self._product_identity_schema_ready:
                ensure_product_archive_identity_schema(connection)
                self._product_identity_schema_ready = True
            GENERAL_CUSTOMER_BRAND_TABLE.create(connection, checkfirst=True)
            GENERAL_CUSTOMER_SHOP_TABLE.create(connection, checkfirst=True)
            GENERAL_CUSTOMER_UNIT_TABLE.create(connection, checkfirst=True)
            GENERAL_CUSTOMER_SORT_PREFERENCE_TABLE.create(connection, checkfirst=True)
            self._ensure_general_customer_schema(connection)
            self._seed_general_customer_shops(connection)
            connection.execute(text("UPDATE inventory_records SET total_count = NULL, warehouse = NULL WHERE document_type IN ('应付款减少', '应付款增加', '应收款减少', '应收款增加') AND (total_count IS NOT NULL OR warehouse IS NOT NULL)"))
            connection.execute(text("""
                UPDATE inventory_records AS record
                SET amount = accounting_amounts.amount
                FROM (
                    SELECT details.document_id, SUM(details.amount) AS amount
                    FROM inventory_details AS details
                    JOIN inventory_records AS source_record ON source_record.id = details.document_id
                    WHERE source_record.document_type IN ('应付款减少', '应付款增加', '应收款减少', '应收款增加')
                      AND details.amount IS NOT NULL
                    GROUP BY details.document_id
                ) AS accounting_amounts
                WHERE record.id = accounting_amounts.document_id
                  AND record.amount IS NULL
                  AND record.deleted_at IS NULL
            """))
            connection.execute(text("UPDATE inventory_records SET total_count = -abs(total_count) WHERE document_type = '进货退货单' AND total_count IS NOT NULL AND total_count > 0"))
            connection.execute(text("UPDATE inventory_records SET amount = -abs(amount) WHERE document_type = '进货退货单' AND amount IS NOT NULL AND amount > 0"))
            connection.execute(text("DELETE FROM inventory_records WHERE deleted_at < now() - interval '10 days'"))

    @staticmethod
    def _seed_account_subjects(connection) -> None:
        defaults = [
            {"code": "0337", "category": "收入类", "name": "罚款收入"},
            {"code": None, "category": "收入类", "name": "付货款"},
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
    def _ensure_supplier_brand_schema(connection) -> None:
        ensure_columns(connection, "supplier_brands", {
            "code": "TEXT", "name": "TEXT", "product_archive_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
            "product_table_name": "TEXT", "sort_order": "INTEGER NOT NULL DEFAULT 0",
        })
        default_brands = (
            ("cbanner_mens", "千百度男鞋"),
            ("cbanner_womens", "千百度女鞋"),
            ("yandou", "烟斗"),
            ("eblan", "伊伴男鞋"),
            ("eblan_womens", "伊伴女鞋"),
            ("smiley", "笑脸"),
            ("ni", "NI"),
        )
        for index, (code, name) in enumerate(default_brands, start=1):
            connection.execute(
                text(
                    """
                    INSERT INTO supplier_brands (code, name, sort_order, product_archive_enabled)
                    VALUES (:code, :name, :sort_order, :product_archive_enabled)
                    ON CONFLICT (code) DO NOTHING
                    """
                ),
                {"code": code, "name": name,
                 "sort_order": index - (code == EBLAN_WOMENS_SUPPLIER_BRAND),
                 "product_archive_enabled": code != EBLAN_WOMENS_SUPPLIER_BRAND},
            )
        connection.execute(text("""
            UPDATE supplier_brands SET name = '伊伴男鞋'
            WHERE code = 'eblan' AND name = '伊伴'
        """))
        manual_brands = connection.execute(text("""
            SELECT id, name
            FROM supplier_brands
            WHERE product_archive_enabled = TRUE
              AND product_table_name IS NULL
              AND code NOT IN ('cbanner_mens', 'cbanner_womens', 'yandou', 'eblan', 'eblan_womens', 'smiley', 'ni')
        """)).mappings().all()
        for brand in manual_brands:
            brand_id = brand["id"]
            legacy_name = f"manual_product_archive_{brand_id}"
            table_name = legacy_name if inspect(connection).has_table(legacy_name) else allocate_product_table_name(
                connection, brand["name"], brand_id,
            )
            connection.execute(
                text("UPDATE supplier_brands SET product_table_name = :table_name WHERE id = :id"),
                {"id": brand_id, "table_name": table_name},
            )
        ensure_not_null(connection, "supplier_brands", "code", "name")
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_brands_code ON supplier_brands (code)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_brands_name ON supplier_brands (name)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_supplier_brands_sort ON supplier_brands (sort_order)"))

    @staticmethod
    def _ensure_warehouse_schema(connection) -> None:
        ensure_columns(connection, "warehouses", {"brand": "TEXT", "sort_order": "INTEGER NOT NULL DEFAULT 0"})
        ensure_columns(connection, "warehouse_brands", {"sort_order": "INTEGER NOT NULL DEFAULT 0"})
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_warehouses_brand_sort ON warehouses (brand, sort_order)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_warehouse_brands_sort ON warehouse_brands (sort_order)"))
        connection.execute(
            text(
                """
                UPDATE warehouse_brands AS target
                SET sort_order = ranked.sort_order
                FROM (
                    SELECT id, row_number() OVER (ORDER BY id) AS sort_order
                    FROM warehouse_brands
                    WHERE sort_order = 0
                ) AS ranked
                WHERE target.id = ranked.id
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE warehouses AS target
                SET sort_order = ranked.sort_order
                FROM (
                    SELECT id, row_number() OVER (PARTITION BY brand ORDER BY id) AS sort_order
                    FROM warehouses
                    WHERE sort_order = 0
                ) AS ranked
                WHERE target.id = ranked.id
                """
            )
        )

    @staticmethod
    def _ensure_supplier_schema(connection) -> None:
        ensure_columns(connection, "suppliers", {"brand": "TEXT", "wechat": "TEXT", "cooperation_status": "TEXT"})
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
                      WHEN (upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
                        OR coalesce(bad.name, '') LIKE '%伊伴%')
                        AND (coalesce(bad.name, '') LIKE '%女鞋%'
                          OR coalesce(bad.name, '') LIKE '%女靴%'
                          OR coalesce(bad.name, '') LIKE '%女士%'
                          OR coalesce(bad.name, '') LIKE '%女款%') THEN 'eblan_womens'
                      WHEN bad.brand = 'eblan' AND (
                          coalesce(bad.name, '') LIKE '%女鞋%'
                          OR coalesce(bad.name, '') LIKE '%女靴%'
                          OR coalesce(bad.name, '') LIKE '%女士%'
                          OR coalesce(bad.name, '') LIKE '%女款%'
                      ) THEN 'eblan_womens'
                      WHEN upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
                        OR coalesce(bad.name, '') LIKE '%伊伴%' THEN 'eblan'
                      WHEN upper(coalesce(bad.name, '')) LIKE '%SMILEY%'
                        OR coalesce(bad.name, '') LIKE '%笑脸%' THEN 'smiley'
                      WHEN upper(btrim(coalesce(bad.name, ''))) ~ '(^|[（([:space:]])NI($|[）)[:space:]])' THEN 'ni'
                      WHEN coalesce(bad.name, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
                      ELSE bad.brand
                  END
                  AND bad.brand IS DISTINCT FROM good.brand
                  AND (
                      upper(coalesce(bad.name, '')) LIKE '%TRUMPPIPE%'
                      OR coalesce(bad.name, '') LIKE '%烟斗%'
                      OR upper(coalesce(bad.name, '')) LIKE '%EBLAN%'
                      OR coalesce(bad.name, '') LIKE '%伊伴%'
                      OR bad.brand = 'eblan' AND (
                          coalesce(bad.name, '') LIKE '%女鞋%'
                          OR coalesce(bad.name, '') LIKE '%女靴%'
                          OR coalesce(bad.name, '') LIKE '%女士%'
                          OR coalesce(bad.name, '') LIKE '%女款%'
                      )
                      OR upper(coalesce(bad.name, '')) LIKE '%SMILEY%'
                      OR coalesce(bad.name, '') LIKE '%笑脸%'
                      OR upper(btrim(coalesce(bad.name, ''))) ~ '(^|[（([:space:]])NI($|[）)[:space:]])'
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
                    WHEN (upper(coalesce(name, '')) LIKE '%EBLAN%'
                      OR coalesce(name, '') LIKE '%伊伴%')
                      AND (coalesce(name, '') LIKE '%女鞋%'
                        OR coalesce(name, '') LIKE '%女靴%'
                        OR coalesce(name, '') LIKE '%女士%'
                        OR coalesce(name, '') LIKE '%女款%') THEN 'eblan_womens'
                    WHEN brand = 'eblan' AND (
                        coalesce(name, '') LIKE '%女鞋%'
                        OR coalesce(name, '') LIKE '%女靴%'
                        OR coalesce(name, '') LIKE '%女士%'
                        OR coalesce(name, '') LIKE '%女款%'
                    ) THEN 'eblan_womens'
                    WHEN upper(coalesce(name, '')) LIKE '%EBLAN%'
                      OR coalesce(name, '') LIKE '%伊伴%' THEN 'eblan'
                    WHEN upper(coalesce(name, '')) LIKE '%SMILEY%'
                      OR coalesce(name, '') LIKE '%笑脸%' THEN 'smiley'
                    WHEN upper(btrim(coalesce(name, ''))) ~ '(^|[（([:space:]])NI($|[）)[:space:]])' THEN 'ni'
                    WHEN coalesce(name, '') LIKE '%千百度品牌方%' THEN :default_brand
                    WHEN coalesce(name, '') LIKE '%千百度女鞋%' THEN 'cbanner_womens'
                    WHEN coalesce(name, '') LIKE '%千百度%' THEN 'cbanner_mens'
                    ELSE :default_brand
                END
                WHERE brand IS NULL
                   OR brand = ''
                   OR (brand IS DISTINCT FROM 'eblan_womens' AND (
                        upper(coalesce(name, '')) LIKE '%TRUMPPIPE%'
                        OR coalesce(name, '') LIKE '%烟斗%'
                        OR upper(coalesce(name, '')) LIKE '%EBLAN%'
                        OR coalesce(name, '') LIKE '%伊伴%'
                        OR brand = 'eblan' AND (
                            coalesce(name, '') LIKE '%女鞋%'
                            OR coalesce(name, '') LIKE '%女靴%'
                            OR coalesce(name, '') LIKE '%女士%'
                            OR coalesce(name, '') LIKE '%女款%'
                        )
                         OR upper(coalesce(name, '')) LIKE '%SMILEY%'
                         OR coalesce(name, '') LIKE '%笑脸%'
                        OR upper(btrim(coalesce(name, ''))) ~ '(^|[（([:space:]])NI($|[）)[:space:]])'
                        OR coalesce(name, '') LIKE '%千百度女鞋%'
                   ))
                """
            ),
            {"default_brand": CBANNER_MENS_BRAND},
        )
        ensure_not_null(connection, "suppliers", "brand")
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
            matching_brands = (EBLAN_BRAND, EBLAN_WOMENS_SUPPLIER_BRAND) if brand in {
                EBLAN_BRAND, EBLAN_WOMENS_SUPPLIER_BRAND,
            } else (brand,)
            exists = connection.execute(
                select(SUPPLIER_TABLE.c.id).where(
                    SUPPLIER_TABLE.c.brand.in_(matching_brands),
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
                connection.execute(
                    insert(GENERAL_CUSTOMER_SHOP_TABLE).values(
                        **row,
                        sort_order=self._next_sort_order(
                            connection,
                            GENERAL_CUSTOMER_SHOP_TABLE,
                            GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name == row["customer_name"],
                        ),
                    )
                )

        existing_brands = connection.execute(select(GENERAL_CUSTOMER_SHOP_TABLE.c.customer_name).distinct()).all()
        for row in existing_brands:
            self._ensure_general_customer_brand(connection, row[0])

    @staticmethod
    def _ensure_general_customer_schema(connection) -> None:
        ensure_columns(connection, "general_customer_shops", {
            "is_active": "BOOLEAN NOT NULL DEFAULT TRUE", "sort_order": "INTEGER NOT NULL DEFAULT 0",
        })
        ensure_columns(connection, "general_customer_brands", {"sort_order": "INTEGER NOT NULL DEFAULT 0"})
        ensure_columns(connection, "general_customer_units", {"sort_order": "INTEGER NOT NULL DEFAULT 0"})
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_general_customer_brands_sort ON general_customer_brands (sort_order)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_general_customer_shops_customer_sort ON general_customer_shops (customer_name, sort_order)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_general_customer_units_shop_sort ON general_customer_units (shop_id, sort_order)"))
        connection.execute(
            text(
                """
                UPDATE general_customer_brands AS target
                SET sort_order = ranked.sort_order
                FROM (
                    SELECT id, row_number() OVER (ORDER BY id) AS sort_order
                    FROM general_customer_brands
                    WHERE sort_order = 0
                ) AS ranked
                WHERE target.id = ranked.id
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE general_customer_shops AS target
                SET sort_order = ranked.sort_order
                FROM (
                    SELECT id, row_number() OVER (PARTITION BY customer_name ORDER BY id) AS sort_order
                    FROM general_customer_shops
                    WHERE sort_order = 0
                ) AS ranked
                WHERE target.id = ranked.id
                """
            )
        )
        connection.execute(
            text(
                """
                UPDATE general_customer_units AS target
                SET sort_order = ranked.sort_order
                FROM (
                    SELECT id, row_number() OVER (PARTITION BY shop_id ORDER BY id) AS sort_order
                    FROM general_customer_units
                    WHERE sort_order = 0
                ) AS ranked
                WHERE target.id = ranked.id
                """
            )
        )

    def _ensure_general_customer_brand(self, connection, name: str) -> None:
        if not name:
            return
        exists = connection.execute(
            select(GENERAL_CUSTOMER_BRAND_TABLE.c.id).where(GENERAL_CUSTOMER_BRAND_TABLE.c.name == name)
        ).first()
        if exists is None:
            connection.execute(
                insert(GENERAL_CUSTOMER_BRAND_TABLE).values(
                    name=name,
                    sort_order=self._next_sort_order(connection, GENERAL_CUSTOMER_BRAND_TABLE),
                )
            )

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
            record["warehouse"] = None
        return record

    @staticmethod
    def _apply_document_total_sign(document_type: object, value: object) -> object:
        if value is None or str(document_type or "").strip() not in NEGATIVE_TOTAL_DOCUMENT_TYPES:
            return value
        decimal_value = Decimal(str(value or "0"))
        return -abs(decimal_value)

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
        else:
            for field in ("total_count", "amount"):
                if field in payload:
                    payload[field] = InventoryRepository._apply_document_total_sign(payload.get("document_type"), payload[field])
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
    def _generate_document_number(
        connection,
        date_value: object,
        document_type: object,
        *,
        sequences: dict[tuple[str, str], int] | None = None,
    ) -> str:
        prefix = InventoryRepository._document_number_prefix(document_type)
        date_text = InventoryRepository._document_number_date_text(date_value)
        key = (prefix, date_text)
        if sequences is not None and key in sequences:
            sequence = sequences[key] + 1
        else:
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
            sequence = max_sequence + 1
        if sequences is not None:
            sequences[key] = sequence
        return f"{prefix}-{date_text}-{sequence:04d}"

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
        occupied_numbers = {
            str(row.get("document_number") or "").strip()
            for row in rows
            if str(row.get("document_number") or "").strip()
        }
        counters: dict[tuple[str, str], int] = {}
        for row in rows:
            existing_number = str(row.get("document_number") or "").strip()
            if existing_number:
                continue
            date_value = row.get("date_value") or row.get("date")
            document_type = row.get("document_type")
            prefix = InventoryRepository._document_number_prefix(document_type)
            date_text = InventoryRepository._document_number_date_text(date_value)
            key = (prefix, date_text)
            sequence = counters.get(key, 0)
            while True:
                sequence += 1
                document_number = InventoryRepository._format_document_number(document_type, date_value, sequence)
                if document_number not in occupied_numbers:
                    break
            counters[key] = sequence
            connection.execute(
                update(INVENTORY_TABLE)
                .where(INVENTORY_TABLE.c.id == row["id"])
                .values(document_number=document_number)
            )
            occupied_numbers.add(document_number)

    @staticmethod
    def _prepare_supplier(data: Mapping[str, object]) -> dict[str, object]:
        name = str(data.get("name") or "").strip()
        brand = str(data.get("brand") or "").strip() or infer_supplier_brand_from_name(name) or CBANNER_MENS_BRAND
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
        return payload
