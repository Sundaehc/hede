from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Identity,
    Integer,
    JSON,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from domain.fields import (
    FieldSpec,
    JST_MONTHLY_ORDER_FIELDS,
    JST_PRICE_FIELDS,
    JST_PURCHASE_DIFF_FIELDS,
    JST_SIZE_STOCK_FIELDS,
    JST_STOCK_SUMMARY_FIELDS,
    VIP_DAILY_CLASSIFY_FIELDS,
    VIP_DAILY_FIELDS,
    VIP_OPS_FIELDS,
    VIP_REALTIME_FIELDS,
)
from domain.schema import METADATA
from domain.vip_sources import (
    VIP_DAILY_TABLE_NAME,
    VIP_OPS_TABLE_NAME,
    VIP_OPS_SNAPSHOT_TABLE_NAME,
    JST_PRICE_TABLE_NAME,
    VIP_REALTIME_TABLE_NAME,
    JST_MONTHLY_ORDERS_TABLE_NAME,
    JST_SIZE_STOCK_TABLE_NAME,
    JST_STOCK_SUMMARY_TABLE_NAME,
    JST_PURCHASE_DIFF_TABLE_NAME,
)


def _col_type(field: FieldSpec):
    if field.type_key == "integer":
        return Integer()
    if field.type_key == "numeric":
        return Numeric(10, 2)
    return Text()


# ── vip_product_daily ──────────────────────────────────────────────

def build_vip_daily_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in VIP_DAILY_FIELDS)
    columns.extend(Column(field.name, _col_type(field)) for field in VIP_DAILY_CLASSIFY_FIELDS)
    columns.append(Column("report_start_date", Date, nullable=True))
    columns.append(Column("report_end_date", Date, nullable=True))
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        VIP_DAILY_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("report_type", "period", "goods_id", name="uq_daily_report_goods"),
    )


# ── vip_product_realtime ───────────────────────────────────────────

def build_vip_realtime_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in VIP_REALTIME_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        VIP_REALTIME_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("goods_id", name="uq_realtime_goods"),
    )


# ── vip_product_ops ────────────────────────────────────────────────

def build_vip_ops_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in VIP_OPS_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        VIP_OPS_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("goods_id", name="uq_ops_goods"),
    )


# ── vip_product_price ──────────────────────────────────────────────

def build_vip_price_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_PRICE_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_PRICE_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("goods_code", "goods_full_name", name="uq_jst_price_code_name"),
    )


VIP_DAILY_TABLE = build_vip_daily_table()
VIP_REALTIME_TABLE = build_vip_realtime_table()
VIP_OPS_TABLE = build_vip_ops_table()


# ── vip_product_ops_snapshots ─────────────────────────────────────

def build_vip_ops_snapshot_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("snapshot_date", Date, nullable=False),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in VIP_OPS_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        VIP_OPS_SNAPSHOT_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("snapshot_date", "goods_id", name="uq_ops_snapshot_date_goods"),
    )


VIP_OPS_SNAPSHOT_TABLE = build_vip_ops_snapshot_table()
JST_PRICE_TABLE = build_vip_price_table()


# ── jst_monthly_orders ────────────────────────────────────────────

def build_jst_monthly_orders_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_MONTHLY_ORDER_FIELDS)
    columns.append(Column("order_time_at", DateTime(timezone=False), nullable=True))
    columns.append(Column("ship_date_value", Date, nullable=True))
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_MONTHLY_ORDERS_TABLE_NAME, METADATA,
        *columns,
    )

JST_MONTHLY_ORDERS_TABLE = build_jst_monthly_orders_table()


# ── jst_size_stock ────────────────────────────────────────────────

def build_jst_size_stock_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_SIZE_STOCK_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_SIZE_STOCK_TABLE_NAME, METADATA,
        *columns,
    )

JST_SIZE_STOCK_TABLE = build_jst_size_stock_table()


# ── jst_stock_summary ────────────────────────────────────────────

def build_jst_stock_summary_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("stock_date", Text, nullable=False),
        Column("stock_date_value", Date, nullable=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_STOCK_SUMMARY_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_STOCK_SUMMARY_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("stock_date", "product_code", name="uq_jst_stock_summary_date_code"),
    )

JST_STOCK_SUMMARY_TABLE = build_jst_stock_summary_table()


# ── jst_purchase_defects ──────────────────────────────────────────

def build_jst_purchase_diff_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_PURCHASE_DIFF_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_PURCHASE_DIFF_TABLE_NAME, METADATA,
        *columns,
    )

JST_PURCHASE_DIFF_TABLE = build_jst_purchase_diff_table()
