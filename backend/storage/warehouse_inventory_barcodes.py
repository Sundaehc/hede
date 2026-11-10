"""Expand recorded stock quantities without inventing sizes or losing balances."""
from __future__ import annotations

from sqlalchemy import JSON, Numeric, Text, case, cast, func, literal, or_, select, true, union_all

from domain.product_size_code import build_product_size_code
from storage.inventory_detail_barcodes import _load_profiles, _text


def expand_stock_sizes(statement, dialect):
    if dialect == "postgresql":
        return _expand_postgres_stock_sizes(statement)
    matches = statement.cte("warehouse_size_matches").prefix_with("MATERIALIZED", dialect="postgresql")
    json_type = func.json_type(matches.c.size_quantities)
    obj = case((json_type == "object", matches.c.size_quantities),
               else_=literal("{}"))
    entries = func.json_each(obj).table_valued("key", "value").alias("warehouse_sizes")
    value = func.trim(cast(entries.c.value, Text))
    quantity = cast(value, Numeric(18, 2))
    sizes = select(matches.c.id, cast(entries.c.key, Text).label("inventory_size_key"), quantity.label("quantity"))\
        .select_from(matches.join(entries, true())).where(quantity != 0).cte("warehouse_recorded_sizes")
    sizes = sizes.prefix_with("MATERIALIZED", dialect="postgresql")
    totals = select(sizes.c.id, func.sum(sizes.c.quantity).label("quantity"), func.count().label("count"))\
        .group_by(sizes.c.id).subquery("warehouse_size_totals")
    residual = matches.c.quantity - func.coalesce(totals.c.quantity, 0)
    units = union_all(
        select(sizes.c.id, sizes.c.inventory_size_key, sizes.c.quantity, literal(False).label("unallocated")),
        select(matches.c.id, literal(""), residual, literal(True))
        .select_from(matches.outerjoin(totals, totals.c.id == matches.c.id))
        .where(or_(residual != 0, func.coalesce(totals.c.count, 0) == 0)),
    ).subquery("warehouse_size_units")
    return select(
        *(column for column in matches.c if column.key not in {"quantity", "size_quantities"}),
        units.c.inventory_size_key, units.c.unallocated, units.c.quantity,
    ).select_from(matches.join(units, units.c.id == matches.c.id)).cte("warehouse_expanded_stock")


def _expand_postgres_stock_sizes(statement):
    """Parse each detail once, retaining only its few size rows while expanding.

    A local window includes a synthetic residual row, so missing/inconsistent
    sizes do not require materializing and joining the entire warehouse twice.
    """
    matches = statement.subquery("warehouse_size_matches")
    obj = case((func.json_typeof(matches.c.size_quantities) == "object", matches.c.size_quantities),
               else_=cast(literal("{}"), JSON))
    entries = func.json_each_text(obj).table_valued("key", "value").alias("warehouse_sizes")
    value = func.trim(cast(entries.c.value, Text))
    quantity = case((value.op("~")(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$"), cast(value, Numeric(18, 2))), else_=0)
    units = union_all(
        select(cast(entries.c.key, Text).label("inventory_size_key"), quantity.label("size_quantity"),
               literal(False).label("unallocated")).select_from(entries).where(quantity != 0).correlate(matches),
        select(literal(""), literal(0), literal(True)),
    ).subquery("warehouse_local_size_units")
    allocated = select(
        units.c.inventory_size_key, units.c.unallocated,
        case((units.c.unallocated, matches.c.quantity - func.sum(units.c.size_quantity).over()),
             else_=units.c.size_quantity).label("quantity"),
        func.count().over().label("unit_count"),
    ).correlate(matches).subquery("warehouse_local_size_balances")
    sizes = select(allocated.c.inventory_size_key, allocated.c.unallocated, allocated.c.quantity)\
        .where(or_(allocated.c.quantity != 0, allocated.c.unit_count == 1)).lateral("warehouse_detail_sizes")
    return select(
        *(column for column in matches.c if column.key not in {"quantity", "size_quantities"}),
        sizes.c.inventory_size_key, sizes.c.unallocated, sizes.c.quantity,
    ).select_from(matches.join(sizes, true())).cte("warehouse_expanded_stock")


def enrich_stock_barcodes(repository, result):
    """Only raw balances are cached; archive rules are resolved afresh per page."""
    items = result["items"]
    with repository.engine.connect() as connection:
        for start in range(0, len(items), 1000):
            batch = items[start:start + 1000]
            profiles, sizes = _load_profiles(connection, batch)
            for item in batch:
                profile, issue = profiles[item["id"]]
                size = sizes.get(_text(profile["size_range"]), {}).get(item["inventory_size_key"]) if profile else None
                color = _text(profile["color_code"]) if profile else ""
                barcode = ""
                if item["unallocated"]:
                    issue = "尺码数量缺失或与明细数量不一致，请核对单据"
                elif profile:
                    rule = _text(profile["barcode_build_rule"])
                    if not _text(profile["sku"]):
                        issue = "请联系商品部维护商品货号"
                    elif rule not in {"货号+尺码", "货号+颜色代码+尺码"}:
                        issue = "请联系商品部维护条码构成逻辑"
                    elif rule == "货号+颜色代码+尺码" and not color:
                        issue = "请联系商品部维护颜色条码"
                    elif not size or not _text(size["barcode"]):
                        issue = "请联系商品部维护尺码组及尺码条码"
                    else:
                        barcode = build_product_size_code(profile["sku"], color, size["barcode"], rule)
                        issue = ""
                item.update(barcode=barcode, color_barcode=color, size_barcode=_text(size["barcode"]) if size else "",
                            size_name=size["size_name"] if size else item["inventory_size_key"], barcode_issue=issue)
    return result
