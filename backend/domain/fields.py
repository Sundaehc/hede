from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    type_key: str = "text"
    aliases: tuple[str, ...] = ()

    @property
    def all_labels(self) -> tuple[str, ...]:
        return (self.label, *self.aliases) if self.label else self.aliases


def field_names(fields: tuple[FieldSpec, ...]) -> list[str]:
    return [field.name for field in fields]


def alias_map(fields: tuple[FieldSpec, ...]) -> dict[str, str]:
    return {
        label: field.name
        for field in fields
        for label in field.all_labels
        if label
    }


PRODUCT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("image_path", "图片"),
    FieldSpec("sku", "货号"),
    FieldSpec("original_sku", "原始货号"),
    FieldSpec("group_name", "组别"),
    FieldSpec("product_level", "商品等级", aliases=("等级", "货品等级")),
    FieldSpec("cost", "成本", "numeric"),
    FieldSpec("factory_sku", "工厂货号"),
    FieldSpec("color", "颜色", aliases=("新色",)),
    FieldSpec("season_category", "季节分类"),
    FieldSpec("year", "年份"),
    FieldSpec("upper_material", "鞋面材质", aliases=("帮面材质",)),
    FieldSpec("lining_material", "内里材质"),
    FieldSpec("outsole_material", "大底材质"),
    FieldSpec("insole_material", "鞋垫材质"),
    FieldSpec("execution_standard", "执行标准", aliases=("执行标",)),
    FieldSpec("heel_height", "跟高"),
    FieldSpec("shoe_width", "鞋宽"),
    FieldSpec("shoe_length", "鞋长"),
    FieldSpec("shaft_circumference", "筒围"),
    FieldSpec("shaft_height", "筒高"),
    FieldSpec("internal_height_increase", "内增高"),
    FieldSpec("internal_height_note", "内增高备注"),
    FieldSpec("upper_height", "鞋帮"),
    FieldSpec("toe_shape", "鞋头", aliases=("鞋头款式",)),
    FieldSpec("closure_type", "闭合方式"),
    FieldSpec("shoe_box_spec", "鞋盒规格"),
    FieldSpec("first_order_time", "首单时间"),
    FieldSpec("size_range", "尺码段", aliases=("码段",)),
    FieldSpec("product_model", "产品型号"),
    FieldSpec("supplier_name", "供应商名", aliases=("供应商",)),
    FieldSpec("color_code", "颜色代码"),
    FieldSpec("launch_date", "上市时间"),
)


INVENTORY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("document_number", "单据编号", aliases=("入库单号", "单据号")),
    FieldSpec("date", "日期"),
    FieldSpec("supplier", "供应商"),
    FieldSpec("total_count", "总数", "numeric"),
    FieldSpec("amount", "金额", "numeric"),
    FieldSpec("warehouse", "仓库"),
    FieldSpec("document_type", "单据类型"),
    FieldSpec("handler", "经手人"),
    FieldSpec("summary", "摘要"),
)

INVENTORY_DETAIL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("product_code", "商品编码"),
    FieldSpec("product_name", "商品名称"),
    FieldSpec("color_spec", "颜色及规格"),
    FieldSpec("color_barcode", "颜色条码"),
    FieldSpec("color_name", "颜色名称"),
    FieldSpec("quantity", "数量", "numeric"),
    FieldSpec("unit_price", "单价", "numeric"),
    FieldSpec("amount", "金额", "numeric"),
)

SUPPLIER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("brand", "品牌"),
    FieldSpec("name", "名称"),
    FieldSpec("factory_code", "工厂代码"),
    FieldSpec("contact", "联系人"),
    FieldSpec("address", "地址"),
    FieldSpec("notes", "备注"),
)

WAREHOUSE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "名称"),
    FieldSpec("address", "地址"),
    FieldSpec("notes", "备注"),
)

GENERAL_CUSTOMER_BRAND_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "品牌"),
)

GENERAL_CUSTOMER_SHOP_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("customer_name", "品牌"),
    FieldSpec("shop_name", "店铺名称"),
)

JST_STOCK_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("stock_date", "库存日期"),
    FieldSpec("product_code", "商品编码"),
    FieldSpec("available_qty", "可用数", "integer", aliases=("可用库存",)),
)


VIP_DAILY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("goods_id", "商品ID"),
    FieldSpec("date", "日期"),
    FieldSpec("goods_name", "商品名称"),
    FieldSpec("goods_code", "货号"),
    FieldSpec("style_code", "款号"),
    FieldSpec("p_spu_id", "P_SPU_ID"),
    FieldSpec("goods_image", "商品图片"),
    FieldSpec("brand_sn", "品牌SN"),
    FieldSpec("brand_name", "品牌名称"),
    FieldSpec("category_l3", "三级分类名称"),
    FieldSpec("first_listing_time", "首次上架时间"),
    FieldSpec("main_style", "主款式"),
    FieldSpec("detail_uv", "商详UV", "integer"),
    FieldSpec("ctr", "CTR(点击PV/曝光PV)"),
    FieldSpec("fav_count", "收藏人数", "integer"),
    FieldSpec("sales_amount", "销售额", "numeric"),
    FieldSpec("sales_volume", "销售量", "integer"),
    FieldSpec("customer_count", "客户数", "integer"),
    FieldSpec("purchase_conversion", "购买转化率(客户数/商详UV)"),
    FieldSpec("reject_count", "拒退件数", "integer"),
    FieldSpec("reject_rate", "拒退率"),
)

VIP_DAILY_CLASSIFY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("report_type", "报表类型"),
    FieldSpec("period", "周期"),
    FieldSpec("date_range", "原始日期区间"),
)

VIP_REALTIME_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("goods_id", "商品ID"),
    FieldSpec("goods_code", "货号"),
    FieldSpec("style_code", "款号"),
    FieldSpec("p_spu_id", "P_SPU_ID"),
    FieldSpec("goods_name", "商品名称"),
    FieldSpec("goods_image", "商品图片"),
    FieldSpec("brand_sn", "品牌SN"),
    FieldSpec("brand_name", "品牌名称"),
    FieldSpec("category_l1", "一级分类名称"),
    FieldSpec("category_l2", "二级分类名称"),
    FieldSpec("category_l3", "三级分类名称"),
    FieldSpec("detail_uv", "商详UV", "integer"),
    FieldSpec("uv_value", "商详UV价值(销售额/商详UV)", "numeric"),
    FieldSpec("sales_amount", "销售额（含拒退）", "numeric"),
    FieldSpec("sales_volume", "销售量（含拒退）", "integer"),
    FieldSpec("customer_count", "客户数", "integer"),
    FieldSpec("purchase_conversion", "购买转化率（%）"),
    FieldSpec("stock_on_sale", "在售库存", "integer"),
)

VIP_OPS_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("goods_code", "货号"),
    FieldSpec("style_code", "款号"),
    FieldSpec("goods_id", "商品ID"),
    FieldSpec("p_spu", "P_SPU"),
    FieldSpec("category_l3", "三级品类"),
    FieldSpec("goods_status", "商品状态"),
    FieldSpec("market_price", "市场价", "numeric"),
    FieldSpec("vip_price", "唯品价", "numeric"),
    FieldSpec("final_price", "到手价", "numeric"),
    FieldSpec("sales_tag", "畅平滞标签"),
    FieldSpec("goods_tag", "商品标签"),
)

JST_PRICE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("goods_code", "货号"),
    FieldSpec("goods_full_name", "商品全名"),
    FieldSpec("stock_qty", "库存数量", "integer"),
    FieldSpec("latest_purchase_price", "最近进价", "numeric"),
    FieldSpec("cost_unit_price", "成本单价", "numeric"),
    FieldSpec("member_price", "会员价", "numeric"),
    FieldSpec("retail_price", "零售价", "numeric"),
    FieldSpec("preset_price_name", "预设售价名称"),
    FieldSpec("preset_price", "预设售价", "numeric"),
    FieldSpec("preset_discount_name", "预设折扣率名称"),
    FieldSpec("preset_discount", "预设折扣率", "numeric"),
    FieldSpec("preset_commission_name", "预设抽成率名称"),
    FieldSpec("preset_commission", "预设抽成率", "numeric"),
)

JST_MONTHLY_ORDER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("internal_order_id", "内部订单号"),
    FieldSpec("online_order_id", "线上订单号"),
    FieldSpec("buyer_account", "买家账号", aliases=("买家帐号",)),
    FieldSpec("platform_site", "平台站点"),
    FieldSpec("order_time", "下单时间"),
    FieldSpec("ship_date", "发货日期"),
    FieldSpec("shop_name", "店铺名称"),
    FieldSpec("payable_amount", "应付金额", "numeric"),
    FieldSpec("paid_amount", "已付金额", "numeric"),
    FieldSpec("status", "状态"),
    FieldSpec("address", "地址", aliases=("地址(包含省市区)",)),
    FieldSpec("order_type", "订单类型"),
    FieldSpec("shop_style_code", "店铺款式编码"),
    FieldSpec("style_code", "款号"),
    FieldSpec("product_code", "商品编码"),
    FieldSpec("quantity", "数量", "integer"),
    FieldSpec("category", "分类"),
    FieldSpec("registered_qty", "登记数量", "integer"),
    FieldSpec("actual_return_qty", "实退数量", "integer"),
    FieldSpec("cost_price", "成本价", "numeric"),
    FieldSpec("shop_status", "店铺状态"),
    FieldSpec("buyer_paid", "买家实付", "numeric"),
    FieldSpec("seller_received", "卖家实收", "numeric"),
    FieldSpec("online_sub_order_id", "线上子订单编号"),
)

JST_SIZE_STOCK_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("product_code", "货号"),
    FieldSpec("size", "尺码"),
    FieldSpec("stock_qty", "库存数量", "integer"),
)

JST_STOCK_SUMMARY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("product_code", "货号"),
    FieldSpec("defect_stock_qty", "次品库存", "integer"),
    FieldSpec("purchase_in_transit_qty", "采购在途数", "integer"),
    FieldSpec("off_shelf_qty", "下架仓", "integer"),
    FieldSpec("order_occupy_qty", "订单占有", "integer"),
)

JST_PURCHASE_DIFF_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("product_code", "货号"),
    FieldSpec("difference_count", "差异数", "integer"),
)


GJ_MERGED_PRODUCT_INFO_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("row_no", "行号", "integer"),
    FieldSpec("goods_code", "货号"),
    FieldSpec("original_goods_code", "原始货号"),
    FieldSpec("goods_full_name", "商品全名"),
    FieldSpec("barcode", "商品条码"),
    FieldSpec("factory_code", "工厂货号"),
    FieldSpec("product_name", "品名"),
    FieldSpec("execution_standard", "执行标准"),
    FieldSpec("barcode_format", "条码格式"),
    FieldSpec("launch_date", "上市日期"),
    FieldSpec("insole_material", "鞋垫材质"),
    FieldSpec("outsole_material", "大底材质"),
    FieldSpec("lining_material", "内里材质"),
    FieldSpec("upper_material", "鞋面材质"),
    FieldSpec("shoe_box_spec", "鞋盒规格"),
    FieldSpec("brand", "品牌"),
    FieldSpec("disabled_flag", "是否停用"),
    FieldSpec("primary_supplier", "主供应商"),
)

