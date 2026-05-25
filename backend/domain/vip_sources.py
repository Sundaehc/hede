from __future__ import annotations

from domain.fields import (
    JST_MONTHLY_ORDER_FIELDS,
    JST_PRICE_FIELDS,
    JST_PURCHASE_DIFF_FIELDS,
    JST_SIZE_STOCK_FIELDS,
    JST_STOCK_SUMMARY_FIELDS,
    VIP_DAILY_CLASSIFY_FIELDS,
    VIP_DAILY_FIELDS,
    VIP_OPS_FIELDS,
    VIP_REALTIME_FIELDS,
    alias_map,
    field_names,
)

# ── Table names ────────────────────────────────────────────────────
VIP_DAILY_TABLE_NAME = "vip_product_daily"
VIP_REALTIME_TABLE_NAME = "vip_product_realtime"
VIP_OPS_TABLE_NAME = "vip_product_ops"
VIP_OPS_SNAPSHOT_TABLE_NAME = "vip_product_ops_snapshots"

# ── vip_product_daily: 环比/罗盘 (3d/7d/1d/30d) 共 21 列 ─────────
VIP_DAILY_COLUMNS: list[str] = field_names(VIP_DAILY_FIELDS)

VIP_DAILY_CLASSIFY_COLUMNS: list[str] = field_names(VIP_DAILY_CLASSIFY_FIELDS)

VIP_DAILY_COLUMN_ALIASES: dict[str, str] = alias_map(VIP_DAILY_FIELDS)

# ── vip_product_realtime: 实时商品 共 18 列 ────────────────────────
VIP_REALTIME_COLUMNS: list[str] = field_names(VIP_REALTIME_FIELDS)

VIP_REALTIME_COLUMN_ALIASES: dict[str, str] = alias_map(VIP_REALTIME_FIELDS)

# ── vip_product_ops: 常态商品运营（仅取 11 列）────────────────────
VIP_OPS_COLUMNS: list[str] = field_names(VIP_OPS_FIELDS)

VIP_OPS_COLUMN_ALIASES: dict[str, str] = alias_map(VIP_OPS_FIELDS)

VIP_OPS_SNAPSHOT_COLUMNS: list[str] = field_names(VIP_OPS_FIELDS)

# ── vip_product_price: 物价信息 共 13 列（跳过行号）──────────────
JST_PRICE_TABLE_NAME = "jst_product_price"

JST_PRICE_COLUMNS: list[str] = field_names(JST_PRICE_FIELDS)

JST_PRICE_COLUMN_ALIASES: dict[str, str] = alias_map(JST_PRICE_FIELDS)

# ── jst_monthly_orders: 月聚水潭订单 共 24 列 ──────────────────────
JST_MONTHLY_ORDERS_TABLE_NAME = "jst_monthly_orders"

JST_MONTHLY_ORDERS_COLUMNS: list[str] = field_names(JST_MONTHLY_ORDER_FIELDS)

JST_MONTHLY_ORDERS_COLUMN_ALIASES: dict[str, str] = alias_map(JST_MONTHLY_ORDER_FIELDS)

# ── Report type / period options ───────────────────────────────────
REPORT_TYPES: tuple[str, ...] = ("环比", "罗盘")
PERIODS: tuple[str, ...] = ("1d", "3d", "7d", "30d")

# ── jst_size_stock: 尺码库存 共 3 列 ───────────────────────────────
JST_SIZE_STOCK_TABLE_NAME = "jst_size_stock"

JST_SIZE_STOCK_COLUMNS: list[str] = field_names(JST_SIZE_STOCK_FIELDS)

# ── jst_stock_summary: 商品库存 Sheet4 汇总 共 5 列 ───────────────
JST_STOCK_SUMMARY_TABLE_NAME = "jst_stock_summary"

JST_STOCK_SUMMARY_COLUMNS: list[str] = field_names(JST_STOCK_SUMMARY_FIELDS)

# ── jst_purchase_defects: 采购次品 共 2 列 ─────────────────────────
JST_PURCHASE_DIFF_TABLE_NAME = "jst_purchase_defects"

JST_PURCHASE_DIFF_COLUMNS: list[str] = field_names(JST_PURCHASE_DIFF_FIELDS)
