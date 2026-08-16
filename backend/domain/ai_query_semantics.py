from __future__ import annotations

import re
from datetime import date

from sqlglot import exp, parse_one


RAW_SOURCE_PATTERNS = (
    re.compile(r"^jst_daily_sales(?:_\d{4})?$"),
    re.compile(r"^vip_daily_sales(?:_\d{4})?$"),
    re.compile(r"^product_goods_historical_sales(?:_\d{4})?$"),
    re.compile(r"^product_goods_historical_orders(?:_\d{4})?$"),
    re.compile(r"^product_goods_detail_snapshots(?:_\d{4})?$"),
    re.compile(r"^fine_table_snapshot_refs_\d{4}$"),
)

RAW_SOURCE_REPLACEMENTS = {
    "jst_aftersale_returns": "v_jst_aftersale_returns_normalized",
    "jst_daily_stock": "v_jst_daily_stock_normalized",
    "jst_monthly_orders": "v_jst_monthly_orders_normalized",
    "jst_product_price": "v_jst_product_price_normalized",
    "vip_product_daily": "v_vip_product_daily_normalized",
    "fine_table_snapshot_metrics": "v_fine_table_snapshot_rows",
    "fine_table_snapshot_payloads": "v_fine_table_snapshot_rows",
}

PRODUCT_ARCHIVE_TABLES = {
    "cbanner_mens_products",
    "cbanner_womens_products",
    "eblan_products",
    "ni_products",
    "smiley_products",
    "yandou_products",
}

DAILY_SALES_TABLES = {"v_jst_daily_sales", "v_vip_daily_sales"}
HISTORICAL_SALES_TABLE = "v_product_goods_historical_sales"
PRECOMPUTED_SALES_TABLE = "product_goods_sales_periods"
CHANNEL_MAPPING_TABLE = "product_goods_shop_channel_mappings"
CURRENT_STOCK_TABLES = {"jst_full_stock", "jst_size_stock", "jst_stock_summary"}
STOCK_SNAPSHOT_TABLES = {
    "jst_size_stock_snapshots",
    "jst_stock_summary_snapshots",
    "v_jst_daily_stock_normalized",
    "v_product_goods_detail_snapshots",
}

QUESTION_BRAND_CODES = (
    ("千百度女鞋", "cbanner_womens"),
    ("千百度男鞋", "cbanner_mens"),
    ("名人烟斗", "yandou"),
    ("烟斗", "yandou"),
    ("伊伴", "eblan"),
    ("笑脸", "smiley"),
    ("小莲", "smiley"),
    ("ni", "ni"),
)
SOURCE_PRODUCT_TABLES = DAILY_SALES_TABLES | {
    "jst_full_stock",
    "jst_size_stock",
    "jst_stock_summary",
}
PRODUCT_CODE_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?=[A-Z0-9]{7,}(?![A-Z0-9]))(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+"
)


class SemanticQueryError(ValueError):
    pass


def is_semantic_source_exposed(table_name: str) -> bool:
    name = table_name.lower()
    if name in RAW_SOURCE_REPLACEMENTS:
        return False
    return not any(pattern.fullmatch(name) for pattern in RAW_SOURCE_PATTERNS)


def referenced_table_names(sql: str) -> set[str]:
    expression = parse_one(sql, read="postgres")
    cte_names = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }
    return {
        table.name.lower()
        for table in expression.find_all(exp.Table)
        if not (
            not table.db
            and not table.catalog
            and table.name.lower() in cte_names
        )
    }


def _question_brand_code(question: str) -> str | None:
    normalized = question.lower()
    for label, code in QUESTION_BRAND_CODES:
        if label.lower() in normalized:
            return code
    return None


def _question_product_codes(question: str) -> set[str]:
    return set(PRODUCT_CODE_PATTERN.findall(question.upper()))


def semantic_rules_for_question(question: str) -> str:
    current_year = date.today().year
    return f"""
业务查询规范（必须遵守）：

一、通用规则
1. 先确定品牌、业务日期、货号/款号、尺码、平台和统计粒度；问题未指定日期时，以相关来源 MAX(业务日期) 为截至日，不直接使用 CURRENT_DATE 假设数据已更新。
2. 品牌内部值固定为：千百度男鞋=cbanner_mens、千百度女鞋=cbanner_womens、烟斗=yandou、伊伴=eblan、笑脸=smiley、NI=ni。brand 条件和店铺映射必须使用内部值，不能写中文品牌简称。
3. 所有商品档案表必须过滤 deleted_at IS NULL。商品档案 sku 使用精确匹配；销售/库存来源中的 product_code、goods_code 往往是“基础货号+颜色/尺码后缀”，查询基础货号时必须用前缀匹配，并在多货号时取最长基础货号命中，不能对来源编码直接等值匹配。
4. 空值表示暂无数据，不能用 0 代替；只有源记录明确为 0 时才能返回 0。例外仅限已有业务公式明确规定的组成字段，例如库存数量各组成列在加法前使用 COALESCE(列, 0)。
5. 当前表和历史快照不能混合求和。需要比较时，必须分别聚合并标明各自日期。
6. 只能使用下方数据库结构中开放的统一视图和业务表，禁止猜测年度分表、父表或底层快照载荷表。

二、销量与订单
1. 聚水潭逐日销量唯一入口为 v_jst_daily_sales，默认销量字段为 net_sales_quantity；sales_quantity 只能表示未扣退货的毛销量。
2. 唯品逐日销量唯一入口为 v_vip_daily_sales，销量字段为 sales_quantity，唯品渠道固定为“唯品”。
3. 2024、2025 历史工作簿销量唯一入口为 v_product_goods_historical_sales，使用 sales_quantity，并必须按 brand 和 sales_date/sales_year 过滤。
4. {current_year} 年及没有完整历史工作簿覆盖的年份使用 v_jst_daily_sales 与 v_vip_daily_sales；不能再叠加同年度历史销量。
5. 同时合并聚水潭与唯品时，唯品日销优先；只有聚水潭记录映射为“唯品”且唯品表中存在同一基础货号、同一 sales_date 的记录时才排除该聚水潭记录，建议使用 NOT EXISTS。不能直接排除全部聚水潭唯品渠道，否则会丢失唯品源缺数日期的销量。
6. 历史订单量只用 v_product_goods_historical_orders.order_quantity；销量不能替代订单量。
7. 年度/月度等预计算指标可用 product_goods_sales_periods，但不能与逐日销量再次相加。

三、平台与赛道
1. 聚水潭平台首先按 product_goods_shop_channel_mappings 查询：mapping.brand 使用上述品牌内部值，mapping.shop_name 对应日销 channel；没有映射时才按 channel 关键词兜底。不要把日销表中的中文 brand 与映射表内部 brand 直接相等关联。
2. 关键词顺序：唯品、天猫、得物、拼多多清仓、拼多多、京东、商品卡、达播清仓、直播赛道、其他。
3. 清仓包括“达播清仓”“拼多多清仓”及渠道名称含“清仓”的记录；直播赛道为映射后的“直播赛道”；传统赛道=总销量-直播-清仓。
4. 工厂渠道历史年份若 v_product_goods_historical_sales 有完整数据，只用历史销量；否则才合并聚水潭净销量和唯品销量。

四、库存
1. 当前货号/尺码库存、在途和库存销售天数优先使用 jst_full_stock，并以 MAX(sync_date) 为当前库存日期；基础货号必须与 jst_full_stock.product_code 做前缀匹配。
2. 在仓库存=COALESCE(actual_stock_qty,0)+COALESCE(purchase_warehouse_stock_qty,0)；在途库存=COALESCE(purchase_in_transit_qty,0)+COALESCE(transfer_in_transit_qty,0)+COALESCE(return_in_transit_qty,0)；整体库存=在仓库存+在途库存。“当前库存”未说明细分时应分别返回这三项，不能只返回 actual_stock_qty。库存组成列必须先逐列 COALESCE 后再相加，避免任一空列令整项结果变空。
3. 当前尺码在仓库存用 jst_size_stock；当前采购在途补充用 jst_stock_summary.purchase_in_transit_qty。不同库存表不能简单相加为同一指标。
4. 指定日期尺码库存用 jst_size_stock_snapshots.snapshot_date；历史完整货品状态用 v_product_goods_detail_snapshots.snapshot_date。
5. 历史日期不得用当前库存表倒推；当前库存与快照库存只能分别比较，不能混合求和。
6. 缺货库存按 available_qty<0 后取其绝对值；断码 SKU 当前没有可靠自动来源，不得用库存为 0 自行推断。

五、精细表与货品表
1. 精细表历史查询使用 v_fine_table_snapshot_rows，并同时按 brand 和 snapshot_date 定位；payload 中的空字段不能自行补 0。
2. 唯品 UV、CTR、收藏、拒退件数和拒退率使用 v_vip_product_daily_normalized，必须说明 report_type、period、report_start_date/report_end_date。
3. 货品表历史经营状态优先使用 v_product_goods_detail_snapshots；手工字段来自 product_goods_overrides，不是商品主档。
4. 补单、补单后库存和补单后周转为人工字段，未填写时保持空值；款号汇总必须在货号数据聚合后求和，不能混入颜色明细行。

六、采购与经营历程
1. 采购权限账户使用 ai_purchase_records 和 ai_purchase_details，它们已强制限定 document_type='进货订单'。
2. 拥有进销存权限时使用 inventory_records 与 inventory_details；有效单据必须过滤 deleted_at IS NULL。
3. 单据明细通过 inventory_details.document_id=inventory_records.id 关联；金额优先使用明细 amount，汇总时避免同时累加单头 amount 和明细 amount。

用户问题：{question}
""".strip()


def validate_semantic_query(question: str, sql: str) -> set[str]:
    tables = referenced_table_names(sql)
    normalized_sql = re.sub(r"\s+", " ", sql).upper()
    errors: list[str] = []
    comparison = any(
        term in question for term in ("对比", "比较", "趋势", "变化", "环比", "分别", "按来源")
    )
    sales_request = any(term in question for term in ("销量", "销售", "卖出", "售出"))
    channel_request = any(
        term in question
        for term in ("平台", "渠道", "传统", "直播", "清仓", "唯品", "天猫", "得物", "拼多多", "京东", "商品卡")
    )

    archive_tables = tables & PRODUCT_ARCHIVE_TABLES
    if archive_tables and not (
        "DELETED_AT" in normalized_sql and re.search(r"DELETED_AT\s+IS\s+NULL", normalized_sql)
    ):
        errors.append("商品档案查询必须过滤 deleted_at IS NULL")

    brand_code = _question_brand_code(question)
    if CHANNEL_MAPPING_TABLE in tables:
        if "BRAND" not in normalized_sql or "SHOP_NAME" not in normalized_sql:
            errors.append("店铺渠道映射必须同时使用 brand 和 shop_name")
        if brand_code and f"'{brand_code.upper()}'" not in normalized_sql:
            errors.append(f"店铺渠道映射的品牌必须使用内部值 {brand_code}")

    if tables & SOURCE_PRODUCT_TABLES:
        for product_code in _question_product_codes(question):
            exact_source_match = re.search(
                rf"(?:\b[A-Z_][A-Z0-9_]*\.)?(?:PRODUCT_CODE|GOODS_CODE)\s*=\s*'{re.escape(product_code)}'",
                normalized_sql,
            )
            if exact_source_match:
                errors.append(
                    f"销售/库存来源货号包含颜色尺码后缀，基础货号 {product_code} 必须使用前缀匹配"
                )

    if "v_jst_daily_sales" in tables and sales_request and "NET_SALES_QUANTITY" not in normalized_sql:
        errors.append("聚水潭销量必须默认使用 net_sales_quantity 净销量")
    if "v_vip_daily_sales" in tables and sales_request and "SALES_QUANTITY" not in normalized_sql:
        errors.append("唯品销量必须使用 sales_quantity")
    if HISTORICAL_SALES_TABLE in tables and sales_request and "SALES_QUANTITY" not in normalized_sql:
        errors.append("历史销量必须使用 sales_quantity")
    if HISTORICAL_SALES_TABLE in tables:
        if "BRAND" not in normalized_sql or not any(
            field in normalized_sql for field in ("SALES_DATE", "SALES_YEAR")
        ):
            errors.append("历史销量必须同时限定 brand 和 sales_date/sales_year")

    if channel_request and "v_jst_daily_sales" in tables and CHANNEL_MAPPING_TABLE not in tables:
        errors.append("聚水潭平台/赛道查询必须优先关联店铺渠道映射表")

    if DAILY_SALES_TABLES <= tables and sales_request and not comparison:
        if CHANNEL_MAPPING_TABLE not in tables:
            errors.append("合并聚水潭与唯品销量时必须先关联店铺渠道映射表")
        has_same_goods_day_match = all(
            field in normalized_sql
            for field in ("SALES_DATE", "PRODUCT_CODE", "GOODS_CODE")
        )
        has_anti_condition = (
            "NOT EXISTS" in normalized_sql
            or bool(re.search(r"NOT\s*\(.*\bEXISTS\s*\(", normalized_sql))
            or ("LEFT JOIN" in normalized_sql and "IS NULL" in normalized_sql)
        )
        has_vip_exclusion = (
            "唯品" in sql and has_same_goods_day_match and has_anti_condition
        )
        if not has_vip_exclusion:
            errors.append("合并聚水潭与唯品销量时必须按同货号同日期排除聚水潭中的重复唯品记录")

    if HISTORICAL_SALES_TABLE in tables and tables & DAILY_SALES_TABLES:
        if "UNION ALL" not in normalized_sql:
            errors.append("历史销量与当年日销只能按不重叠日期 UNION ALL，不能直接 JOIN 或相加")
        if not any(term in question for term in ("历年", "全部年份", "总销量", "2024", "2025")):
            errors.append("当前查询没有跨历史年份需求，不应混用历史销量和当年日销")

    if PRECOMPUTED_SALES_TABLE in tables and tables & (
        DAILY_SALES_TABLES | {HISTORICAL_SALES_TABLE}
    ) and not comparison:
        errors.append("预计算期间销量不能与逐日/历史销量再次相加")

    if tables & CURRENT_STOCK_TABLES and tables & STOCK_SNAPSHOT_TABLES and not comparison:
        errors.append("当前库存与历史快照不能在同一指标中混合计算")

    if "jst_full_stock" in tables and not comparison:
        if "SYNC_DATE" not in normalized_sql or "MAX" not in normalized_sql:
            errors.append("当前全量库存必须限定为 MAX(sync_date)")
        inventory_components = sum(
            field in normalized_sql
            for field in (
                "ACTUAL_STOCK_QTY",
                "PURCHASE_WAREHOUSE_STOCK_QTY",
                "PURCHASE_IN_TRANSIT_QTY",
                "TRANSFER_IN_TRANSIT_QTY",
                "RETURN_IN_TRANSIT_QTY",
            )
        )
        if inventory_components > 1 and "COALESCE" not in normalized_sql:
            errors.append("库存组成字段相加前必须逐列使用 COALESCE(字段, 0)")

    snapshot_tables = tables & STOCK_SNAPSHOT_TABLES
    if snapshot_tables and "SNAPSHOT_DATE" not in normalized_sql and "STOCK_DATE_VALUE" not in normalized_sql:
        errors.append("库存或货品快照查询必须明确快照日期字段")

    if "v_fine_table_snapshot_rows" in tables:
        if "SNAPSHOT_DATE" not in normalized_sql or "BRAND" not in normalized_sql:
            errors.append("精细表历史查询必须同时限定 brand 和 snapshot_date")

    if "v_vip_product_daily_normalized" in tables:
        if "REPORT_TYPE" not in normalized_sql or "PERIOD" not in normalized_sql:
            errors.append("唯品周期指标必须同时限定 report_type 和 period")

    if "inventory_records" in tables:
        if "DELETED_AT" not in normalized_sql or not re.search(
            r"DELETED_AT\s+IS\s+NULL", normalized_sql
        ):
            errors.append("单据查询必须过滤 deleted_at IS NULL")

    if errors:
        raise SemanticQueryError("；".join(dict.fromkeys(errors)))

    return tables
