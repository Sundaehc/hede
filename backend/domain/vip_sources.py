from __future__ import annotations

# ── Table names ────────────────────────────────────────────────────
VIP_DAILY_TABLE_NAME = "vip_product_daily"
VIP_REALTIME_TABLE_NAME = "vip_product_realtime"
VIP_OPS_TABLE_NAME = "vip_product_ops"

# ── vip_product_daily: 环比/罗盘 (3d/7d/1d/30d) 共 21 列 ─────────
VIP_DAILY_COLUMNS: list[str] = [
    "goods_id",             # 商品ID
    "date",                 # 日期
    "goods_name",           # 商品名称
    "goods_code",           # 货号
    "style_code",           # 款号
    "p_spu_id",             # P_SPU_ID
    "goods_image",          # 商品图片
    "brand_sn",             # 品牌SN
    "brand_name",           # 品牌名称
    "category_l3",          # 三级分类名称
    "first_listing_time",   # 首次上架时间
    "main_style",           # 主款式
    "detail_uv",            # 商详UV
    "ctr",                  # CTR(点击PV/曝光PV)
    "fav_count",            # 收藏人数
    "sales_amount",         # 销售额
    "sales_volume",         # 销售量
    "customer_count",       # 客户数
    "purchase_conversion",  # 购买转化率(客户数/商详UV)
    "reject_count",         # 拒退件数
    "reject_rate",          # 拒退率
]

VIP_DAILY_CLASSIFY_COLUMNS: list[str] = [
    "report_type",  # 环比 / 罗盘
    "period",       # 1d / 3d / 7d / 30d
    "date_range",   # 原始日期区间
]

VIP_DAILY_COLUMN_ALIASES: dict[str, str] = {
    "商品ID": "goods_id",
    "日期": "date",
    "商品名称": "goods_name",
    "货号": "goods_code",
    "款号": "style_code",
    "P_SPU_ID": "p_spu_id",
    "商品图片": "goods_image",
    "品牌SN": "brand_sn",
    "品牌名称": "brand_name",
    "三级分类名称": "category_l3",
    "首次上架时间": "first_listing_time",
    "主款式": "main_style",
    "商详UV": "detail_uv",
    "CTR(点击PV/曝光PV)": "ctr",
    "收藏人数": "fav_count",
    "销售额": "sales_amount",
    "销售量": "sales_volume",
    "客户数": "customer_count",
    "购买转化率(客户数/商详UV)": "purchase_conversion",
    "拒退件数": "reject_count",
    "拒退率": "reject_rate",
}

# ── vip_product_realtime: 实时商品 共 18 列 ────────────────────────
VIP_REALTIME_COLUMNS: list[str] = [
    "goods_id",             # 商品ID
    "goods_code",           # 货号
    "style_code",           # 款号
    "p_spu_id",             # P_SPU_ID
    "goods_name",           # 商品名称
    "goods_image",          # 商品图片
    "brand_sn",             # 品牌SN
    "brand_name",           # 品牌名称
    "category_l1",          # 一级分类名称
    "category_l2",          # 二级分类名称
    "category_l3",          # 三级分类名称
    "detail_uv",            # 商详UV
    "uv_value",             # 商详UV价值(销售额/商详UV)
    "sales_amount",         # 销售额（含拒退）
    "sales_volume",         # 销售量（含拒退）
    "customer_count",       # 客户数
    "purchase_conversion",  # 购买转化率（%）
    "stock_on_sale",        # 在售库存
]

VIP_REALTIME_COLUMN_ALIASES: dict[str, str] = {
    "商品ID": "goods_id",
    "货号": "goods_code",
    "款号": "style_code",
    "P_SPU_ID": "p_spu_id",
    "商品名称": "goods_name",
    "商品图片": "goods_image",
    "品牌SN": "brand_sn",
    "品牌名称": "brand_name",
    "一级分类名称": "category_l1",
    "二级分类名称": "category_l2",
    "三级分类名称": "category_l3",
    "商详UV": "detail_uv",
    "商详UV价值(销售额/商详UV)": "uv_value",
    "销售额（含拒退）": "sales_amount",
    "销售量（含拒退）": "sales_volume",
    "客户数": "customer_count",
    "购买转化率（%）": "purchase_conversion",
    "在售库存": "stock_on_sale",
}

# ── vip_product_ops: 常态商品运营（仅取 11 列）────────────────────
VIP_OPS_COLUMNS: list[str] = [
    "goods_code",       # 货号
    "style_code",       # 款号
    "goods_id",         # 商品ID
    "p_spu",            # P_SPU
    "category_l3",      # 三级品类
    "goods_status",     # 商品状态
    "market_price",     # 市场价
    "vip_price",        # 唯品价
    "final_price",      # 到手价
    "sales_tag",        # 畅平滞标签
    "goods_tag",        # 商品标签
]

VIP_OPS_COLUMN_ALIASES: dict[str, str] = {
    "货号": "goods_code",
    "款号": "style_code",
    "商品ID": "goods_id",
    "P_SPU": "p_spu",
    "三级品类": "category_l3",
    "商品状态": "goods_status",
    "市场价": "market_price",
    "唯品价": "vip_price",
    "到手价": "final_price",
    "畅平滞标签": "sales_tag",
    "商品标签": "goods_tag",
}

# ── Report type / period options ───────────────────────────────────
REPORT_TYPES: tuple[str, ...] = ("环比", "罗盘")
PERIODS: tuple[str, ...] = ("1d", "3d", "7d", "30d")
