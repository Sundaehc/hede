from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
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

from domain.schema import METADATA
from domain.vip_sources import (
    VIP_DAILY_CLASSIFY_COLUMNS,
    VIP_DAILY_COLUMNS,
    VIP_DAILY_TABLE_NAME,
    VIP_OPS_COLUMNS,
    VIP_OPS_TABLE_NAME,
    JST_PRICE_COLUMNS,
    JST_PRICE_TABLE_NAME,
    VIP_REALTIME_COLUMNS,
    VIP_REALTIME_TABLE_NAME,
)


def _col_type(name: str):
    integer_cols = {
        "detail_uv", "fav_count", "sales_volume", "customer_count",
        "reject_count", "stock_on_sale", "stock_qty",
    }
    numeric_cols = {
        "sales_amount", "uv_value",
        "market_price", "vip_price", "final_price",
        "latest_purchase_price", "cost_unit_price", "member_price",
        "retail_price", "preset_price", "preset_discount", "preset_commission",
    }
    if name in integer_cols:
        return Integer
    if name in numeric_cols:
        return Numeric(10, 2)
    return Text


# ── vip_product_daily ──────────────────────────────────────────────

def build_vip_daily_table() -> Table:
    columns: list = [
        Column("id", BigInteger, Identity(always=False), primary_key=True),
        Column("source_workbook", Text, nullable=False, default=""),
        Column("source_sheet", Text, nullable=False, default=""),
        Column("source_row_number", Text, nullable=False, default=""),
        Column("raw_payload", JSON, nullable=False, default=dict),
    ]
    columns.extend(Column(name, _col_type(name)) for name in VIP_DAILY_COLUMNS)
    columns.extend(Column(name, Text()) for name in VIP_DAILY_CLASSIFY_COLUMNS)
    columns.append(Column("extra_fields", JSON, nullable=True))
    columns.append(Column("created_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now())))
    columns.append(Column("updated_at", DateTime(timezone=True), server_default=func.date_trunc('minute', func.now()), onupdate=func.date_trunc('minute', func.now())))
    return Table(
        VIP_DAILY_TABLE_NAME, METADATA,
        *columns,
        UniqueConstraint("report_type", "period", "date_range", "goods_id", name="uq_daily_report_goods"),
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
    columns.extend(Column(name, _col_type(name)) for name in VIP_REALTIME_COLUMNS)
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
    columns.extend(Column(name, _col_type(name)) for name in VIP_OPS_COLUMNS)
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
    columns.extend(Column(name, _col_type(name)) for name in JST_PRICE_COLUMNS)
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
JST_PRICE_TABLE = build_vip_price_table()
