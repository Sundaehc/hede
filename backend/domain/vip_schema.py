from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Identity,
    Index,
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
    JST_AFTERSALE_RETURN_FIELDS,
    JST_MONTHLY_ORDER_FIELDS,
    JST_PRICE_FIELDS,
    JST_PRODUCT_PROFILE_FIELDS,
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
    VIP_DAILY_SNAPSHOT_TABLE_NAME,
    VIP_OPS_TABLE_NAME,
    VIP_OPS_SNAPSHOT_TABLE_NAME,
    JST_PRICE_TABLE_NAME,
    VIP_REALTIME_TABLE_NAME,
    JST_MONTHLY_ORDERS_TABLE_NAME,
    JST_SIZE_STOCK_TABLE_NAME,
    JST_STOCK_SUMMARY_TABLE_NAME,
    JST_PURCHASE_DIFF_TABLE_NAME,
    JST_PRODUCT_PROFILE_TABLE_NAME,
    JST_AFTERSALE_RETURN_TABLE_NAME,
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
        Column("source_date", Text, nullable=False, default=""),
        Column("source_date_value", Date, nullable=True),
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
        UniqueConstraint("source_date", "goods_code", "goods_full_name", name="uq_jst_price_date_code_name"),
    )


VIP_DAILY_TABLE = build_vip_daily_table()
Index(
    "idx_vip_daily_goods_code_report_updated",
    VIP_DAILY_TABLE.c.goods_code,
    VIP_DAILY_TABLE.c.report_end_date.desc(),
    VIP_DAILY_TABLE.c.updated_at.desc(),
    VIP_DAILY_TABLE.c.id.desc(),
)


# ── vip_product_daily_snapshots ───────────────────────────────────

def build_vip_daily_snapshot_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("snapshot_date", Date, nullable=False),
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
        VIP_DAILY_SNAPSHOT_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("snapshot_date", "goods_id", name="uq_daily_snapshot_date_goods"),
    )


VIP_DAILY_SNAPSHOT_TABLE = build_vip_daily_snapshot_table()
Index(
    "idx_daily_snapshots_code_type_period_date",
    VIP_DAILY_SNAPSHOT_TABLE.c.goods_code,
    VIP_DAILY_SNAPSHOT_TABLE.c.report_type,
    VIP_DAILY_SNAPSHOT_TABLE.c.period,
    VIP_DAILY_SNAPSHOT_TABLE.c.snapshot_date,
)
VIP_REALTIME_TABLE = build_vip_realtime_table()
VIP_OPS_TABLE = build_vip_ops_table()
Index(
    "idx_vip_ops_goods_code_updated",
    VIP_OPS_TABLE.c.goods_code,
    VIP_OPS_TABLE.c.updated_at.desc(),
    VIP_OPS_TABLE.c.id.desc(),
)


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
Index(
    "idx_jst_price_code_date_updated",
    JST_PRICE_TABLE.c.goods_code,
    JST_PRICE_TABLE.c.source_date_value.desc(),
    JST_PRICE_TABLE.c.updated_at.desc(),
    JST_PRICE_TABLE.c.id.desc(),
)


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
Index(
    "idx_jst_monthly_orders_style_time",
    JST_MONTHLY_ORDERS_TABLE.c.style_code,
    JST_MONTHLY_ORDERS_TABLE.c.order_time_at,
)


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
Index(
    "idx_jst_size_stock_product_size",
    JST_SIZE_STOCK_TABLE.c.product_code,
    JST_SIZE_STOCK_TABLE.c.size,
)


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
Index("idx_jst_stock_summary_product_code", JST_STOCK_SUMMARY_TABLE.c.product_code)


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
Index("idx_jst_purchase_defects_product_code", JST_PURCHASE_DIFF_TABLE.c.product_code)


# ── jst_product_profiles ─────────────────────────────────────────

def build_jst_product_profile_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_PRODUCT_PROFILE_FIELDS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_PRODUCT_PROFILE_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("product_code", name="uq_jst_product_profiles_product_code"),
    )


JST_PRODUCT_PROFILE_TABLE = build_jst_product_profile_table()
Index("idx_jst_product_profiles_style_code", JST_PRODUCT_PROFILE_TABLE.c.style_code)
Index("idx_jst_product_profiles_color_name", JST_PRODUCT_PROFILE_TABLE.c.color_name)


# ── jst_aftersale_returns ─────────────────────────────────────────

def build_jst_aftersale_return_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(field.name, _col_type(field)) for field in JST_AFTERSALE_RETURN_FIELDS)
    columns.append(Column("order_date_value", Date, nullable=True))
    columns.append(Column("order_time_value", Date, nullable=True))
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        JST_AFTERSALE_RETURN_TABLE_NAME, METADATA,
        *columns,
    )


JST_AFTERSALE_RETURN_TABLE = build_jst_aftersale_return_table()
Index("idx_jst_aftersale_returns_original_code", JST_AFTERSALE_RETURN_TABLE.c.original_goods_code)
Index("idx_jst_aftersale_returns_order_date", JST_AFTERSALE_RETURN_TABLE.c.order_date_value)
Index("idx_jst_aftersale_returns_order_time", JST_AFTERSALE_RETURN_TABLE.c.order_time_value)
