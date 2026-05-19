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

# ── vip_product_price: 物价信息 共 13 列（跳过行号）──────────────
JST_PRICE_TABLE_NAME = "jst_product_price"

JST_PRICE_COLUMNS: list[str] = [
    "goods_code",              # 货号
    "goods_full_name",         # 商品全名
    "stock_qty",               # 库存数量
    "latest_purchase_price",   # 最近进价
    "cost_unit_price",         # 成本单价
    "member_price",            # 会员价
    "retail_price",            # 零售价
    "preset_price_name",       # 预设售价名称
    "preset_price",            # 预设售价
    "preset_discount_name",    # 预设折扣率名称
    "preset_discount",         # 预设折扣率
    "preset_commission_name",  # 预设抽成率名称
    "preset_commission",       # 预设抽成率
]

JST_PRICE_COLUMN_ALIASES: dict[str, str] = {
    "货号": "goods_code",
    "商品全名": "goods_full_name",
    "库存数量": "stock_qty",
    "最近进价": "latest_purchase_price",
    "成本单价": "cost_unit_price",
    "会员价": "member_price",
    "零售价": "retail_price",
    "预设售价名称": "preset_price_name",
    "预设售价": "preset_price",
    "预设折扣率名称": "preset_discount_name",
    "预设折扣率": "preset_discount",
    "预设抽成率名称": "preset_commission_name",
    "预设抽成率": "preset_commission",
}

# ── jst_monthly_orders: 月聚水潭订单 共 24 列 ──────────────────────
JST_MONTHLY_ORDERS_TABLE_NAME = "jst_monthly_orders"

JST_MONTHLY_ORDERS_COLUMNS: list[str] = [
    "internal_order_id",     # 内部订单号
    "online_order_id",       # 线上订单号
    "buyer_account",         # 买家账号
    "platform_site",         # 平台站点
    "order_time",            # 下单时间
    "ship_date",             # 发货日期
    "shop_name",             # 店铺名称
    "payable_amount",        # 应付金额
    "paid_amount",           # 已付金额
    "status",                # 状态
    "address",               # 地址
    "order_type",            # 订单类型
    "shop_style_code",       # 店铺款式编码
    "style_code",            # 款号
    "product_code",          # 商品编码
    "quantity",              # 数量
    "category",              # 分类
    "registered_qty",        # 登记数量
    "actual_return_qty",     # 实退数量
    "cost_price",            # 成本价
    "shop_status",           # 店铺状态
    "buyer_paid",            # 买家实付
    "seller_received",       # 卖家实收
    "online_sub_order_id",   # 线上子订单编号
]

JST_MONTHLY_ORDERS_COLUMN_ALIASES: dict[str, str] = {
    "内部订单号": "internal_order_id",
    "线上订单号": "online_order_id",
    "买家账号": "buyer_account",
    "买家帐号": "buyer_account",
    "平台站点": "platform_site",
    "下单时间": "order_time",
    "发货日期": "ship_date",
    "店铺名称": "shop_name",
    "应付金额": "payable_amount",
    "已付金额": "paid_amount",
    "状态": "status",
    "地址": "address",
    "地址(包含省市区)": "address",
    "订单类型": "order_type",
    "店铺款式编码": "shop_style_code",
    "款号": "style_code",
    "商品编码": "product_code",
    "数量": "quantity",
    "分类": "category",
    "登记数量": "registered_qty",
    "实退数量": "actual_return_qty",
    "成本价": "cost_price",
    "店铺状态": "shop_status",
    "买家实付": "buyer_paid",
    "卖家实收": "seller_received",
    "线上子订单编号": "online_sub_order_id",
}

# ── Report type / period options ───────────────────────────────────
REPORT_TYPES: tuple[str, ...] = ("环比", "罗盘")
PERIODS: tuple[str, ...] = ("1d", "3d", "7d", "30d")
