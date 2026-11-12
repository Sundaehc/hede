"""Read-only, paged size expansion for inbound and sales product details."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import JSON, MetaData, Numeric, Text, and_, case, cast, func, literal, or_, select, true, union_all
from sqlalchemy.sql import visitors

from domain.inventory_numeric import INVENTORY_NUMBER_PRECISION, INVENTORY_NUMBER_SCALE
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from domain.product_archive_naming import manual_product_table_name
from domain.product_size_code import build_product_size_code
from domain.schema import PRODUCT_ARCHIVE_TABLES, build_product_archive_table
from domain.size_group_schema import SIZE_GROUP_ITEMS_TABLE, SIZE_GROUPS_TABLE
from storage.detail_selection import selected_detail_values
from storage.warehouse_inventory_cache import InventoryGroups


def _text(value):
    return "" if value is None else str(value).strip()


def _barcode_statements(connection, criterion, signed_quantity, signed_amount, return_type, is_sales, direction, page, page_size, size_name, selected_rows=None, cached_totals=None):
    if connection.dialect.name == "postgresql" and not size_name and selected_rows is None:
        return _paged_postgres_barcode_statement(
            criterion, signed_quantity, signed_amount, return_type, is_sales, direction, page, page_size, cached_totals,
        )
    detail, record = INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
    matches = select(
        detail.c.id.label("detail_id"), detail.c.size_quantities,
        record.c.document_type, record.c.date_value, record.c.date, record.c.document_number,
        signed_quantity.label("parent_quantity"), signed_amount.label("parent_amount"),
    ).select_from(detail.join(record, record.c.id == detail.c.document_id)).where(criterion).cte("barcode_detail_matches")
    postgres = connection.dialect.name == "postgresql"
    if postgres:
        matches = matches.prefix_with("MATERIALIZED")
    json_type = func.json_typeof(matches.c.size_quantities) if postgres else func.json_type(matches.c.size_quantities)
    size_json = case((json_type == "object", matches.c.size_quantities), else_=cast(literal("{}"), JSON) if postgres else literal("{}"))
    size_entries = (func.json_each_text(size_json) if postgres else func.json_each(size_json)).table_valued("key", "value")
    if postgres:
        size_entries = size_entries.lateral("detail_sizes")
    else:
        size_entries = size_entries.alias("detail_sizes")
    value = func.trim(cast(size_entries.c.value, Text))
    numeric = Numeric(INVENTORY_NUMBER_PRECISION, INVENTORY_NUMBER_SCALE)
    size_quantity = cast(value, numeric)
    if postgres:
        # Legacy JSON can contain blank or non-numeric values. Preserve its
        # parent quantity in the unallocated row instead of failing the report.
        size_quantity = case((value.op("~")(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$"), size_quantity), else_=0)
    size_quantity = case(
        (matches.c.document_type == return_type, -func.abs(size_quantity) if is_sales else -size_quantity),
        else_=size_quantity,
    )
    sizes = select(
        matches.c.detail_id, cast(size_entries.c.key, Text).label("size_name"),
        size_quantity.label("quantity"),
    ).select_from(matches.join(size_entries, true())).where(size_quantity != 0).cte("barcode_recorded_sizes")
    if postgres:
        sizes = sizes.prefix_with("MATERIALIZED")
    size_totals = select(
        sizes.c.detail_id, func.sum(sizes.c.quantity).label("quantity"), func.count().label("count"),
    ).group_by(sizes.c.detail_id).subquery("barcode_size_totals")
    residual = matches.c.parent_quantity - func.coalesce(size_totals.c.quantity, 0)
    units = union_all(
        select(sizes.c.detail_id, sizes.c.size_name, sizes.c.quantity, literal(0).label("unallocated")),
        select(matches.c.detail_id, literal("").label("size_name"), residual.label("quantity"), literal(1).label("unallocated"))
        .select_from(matches.outerjoin(size_totals, size_totals.c.detail_id == matches.c.detail_id))
        .where(or_(residual != 0, func.coalesce(size_totals.c.count, 0) == 0,
                   and_(matches.c.parent_quantity == 0, matches.c.parent_amount != 0))),
    ).subquery("barcode_units")
    cumulative = func.sum(units.c.quantity).over(
        partition_by=units.c.detail_id, order_by=(units.c.unallocated, units.c.size_name), rows=(None, 0),
    )
    # Differences of rounded cumulative allocations keep every original cent,
    # including discounts and quantities inconsistent with legacy size JSON.
    divisor = func.nullif(matches.c.parent_quantity, 0)
    amount = case(
        (matches.c.parent_quantity == 0, case((units.c.unallocated == 1, matches.c.parent_amount), else_=0)),
        else_=(func.round(matches.c.parent_amount * cumulative / divisor, 2)
               - func.round(matches.c.parent_amount * (cumulative - units.c.quantity) / divisor, 2)),
    )
    lines = select(
        units.c.detail_id, units.c.size_name, units.c.quantity, units.c.unallocated, amount.label("amount"),
        matches.c.date_value, matches.c.date, matches.c.document_number,
    ).select_from(units.join(matches, units.c.detail_id == matches.c.detail_id)).cte("barcode_lines")
    if size_name:
        lines = select(lines).where(lines.c.size_name == size_name.strip()).cte("barcode_filtered_lines")
    if selected_rows is not None:
        row_key = cast(lines.c.detail_id, Text) + ":" + cast(lines.c.unallocated, Text) + ":" + lines.c.size_name
        lines = select(lines).where(row_key.in_(selected_detail_values(
            selected_rows, connection.dialect.name,
        ))).cte("barcode_selected_lines")
    totals = select(
        func.count().label("detail_count"), func.coalesce(func.sum(lines.c.quantity), 0).label("quantity_total"),
        func.coalesce(func.sum(lines.c.amount), 0).label("amount_total"),
    ).subquery("barcode_totals")

    def order(columns):
        date_value = columns.date_value.desc() if direction == "desc" else columns.date_value.asc()
        raw_date = columns.date.desc() if direction == "desc" else columns.date.asc()
        return date_value.nulls_last(), raw_date.nulls_last(), columns.document_number, columns.detail_id, columns.unallocated, columns.size_name

    paged = select(lines).order_by(*order(lines.c)).offset((page - 1) * page_size).limit(page_size).cte("barcode_page")
    source = totals.outerjoin(paged, true()).outerjoin(detail, detail.c.id == paged.c.detail_id).outerjoin(record, record.c.id == detail.c.document_id)
    return select(
        detail.c.id, detail.c.document_id, detail.c.product_identity_id, detail.c.product_code,
        detail.c.product_name, detail.c.color_name, detail.c.color_spec, detail.c.unit_price,
        paged.c.size_name, paged.c.unallocated, paged.c.quantity, paged.c.amount,
        record.c.document_type, record.c.document_number, record.c.date, record.c.supplier, record.c.warehouse,
        totals.c.detail_count, totals.c.quantity_total, totals.c.amount_total,
    ).select_from(source).order_by(*order(paged.c))


def _paged_postgres_barcode_statement(criterion, signed_quantity, signed_amount, return_type, is_sales, direction, page, page_size, cached_totals=None):
    """Count repeated distributions once; allocate cents only for page parents.

    Sorting a compact parent index avoids a global expanded-size amount window
    and its temporary files. Each parent contributes at least one size line.
    """
    detail, record = INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
    document_conditions, detail_conditions = [], []
    for condition in criterion.clauses:
        target = detail_conditions if any(getattr(node, "table", None) is detail for node in visitors.iterate(condition)) else document_conditions
        target.append(condition)
    documents = select(record.c.id, record.c.document_type, record.c.date_value, record.c.date, record.c.document_number)\
        .where(*document_conditions).cte("barcode_documents").prefix_with("MATERIALIZED")
    def replace_record(node):
        if getattr(node, "table", None) is record:
            return documents.c[node.key]
    signed_quantity = visitors.replacement_traverse(signed_quantity, {}, replace_record)
    signed_amount = visitors.replacement_traverse(signed_amount, {}, replace_record)
    matches = select(
        detail.c.id.label("detail_id"), detail.c.size_quantities,
        documents.c.document_type, documents.c.date_value, documents.c.date, documents.c.document_number,
        signed_quantity.label("parent_quantity"), signed_amount.label("parent_amount"),
    ).select_from(detail.join(documents, documents.c.id == detail.c.document_id)).where(*detail_conditions)
    matches = matches.subquery("barcode_parent_matches")

    def sizes_for(parent, name):
        obj = case((func.json_typeof(parent.c.size_quantities) == "object", parent.c.size_quantities),
                   else_=cast(literal("{}"), JSON))
        entries = func.json_each_text(obj).table_valued("key", "value").alias(name)
        value = func.trim(cast(entries.c.value, Text))
        quantity = case((value.op("~")(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$"),
                         cast(value, Numeric(INVENTORY_NUMBER_PRECISION, INVENTORY_NUMBER_SCALE))), else_=0)
        quantity = case((parent.c.document_type == return_type, -func.abs(quantity) if is_sales else -quantity), else_=quantity)
        return entries, quantity

    size_text = func.coalesce(cast(matches.c.size_quantities, Text), literal("null"))
    force_residual = and_(matches.c.parent_quantity == 0, matches.c.parent_amount != 0)
    distributions = select(
        size_text.label("size_text"), matches.c.document_type, matches.c.parent_quantity,
        force_residual.label("force_residual"),
        func.count().label("parent_count"), func.sum(matches.c.parent_quantity).label("quantity_total"),
        func.sum(matches.c.parent_amount).label("amount_total"),
    ).group_by(size_text, matches.c.document_type, matches.c.parent_quantity,
               force_residual).cte("barcode_distributions").prefix_with("MATERIALIZED")
    grouped_parents = select(
        distributions, cast(distributions.c.size_text, JSON).label("size_quantities"),
    ).subquery("barcode_grouped_parents")
    entries, quantity = sizes_for(grouped_parents, "barcode_count_sizes")
    summary = select(func.count().label("size_count"), func.coalesce(func.sum(quantity), 0).label("size_quantity"))\
        .select_from(entries).where(quantity != 0).correlate(grouped_parents).lateral("barcode_parent_size_summary")
    residual = grouped_parents.c.parent_quantity - summary.c.size_quantity
    has_residual = or_(residual != 0, summary.c.size_count == 0,
                       grouped_parents.c.force_residual)

    def parent_order(columns):
        return (
            (columns.date_value.desc() if direction == "desc" else columns.date_value.asc()).nulls_last(),
            (columns.date.desc() if direction == "desc" else columns.date.asc()).nulls_last(),
            columns.document_number, columns.detail_id,
        )

    totals = select(
        func.coalesce(func.sum(grouped_parents.c.parent_count * (summary.c.size_count + case((has_residual, 1), else_=0))), 0).label("detail_count"),
        func.coalesce(func.sum(grouped_parents.c.quantity_total), 0).label("quantity_total"),
        func.coalesce(func.sum(grouped_parents.c.amount_total), 0).label("amount_total"),
    ).select_from(grouped_parents.join(summary, true())).subquery("barcode_totals")
    if cached_totals is not None:
        totals = select(
            literal(cached_totals["detail_count"]).label("detail_count"),
            literal(Decimal(cached_totals["quantity_total"])).label("quantity_total"),
            literal(Decimal(cached_totals["amount_total"])).label("amount_total"),
        ).subquery("barcode_totals")
    offset = (page - 1) * page_size
    # Every parent produces at least one line, so no page needs more than this
    # many parents. Never sort/allocate all historical expanded size lines.
    chosen = select(matches).order_by(*parent_order(matches.c)).limit(offset + page_size)\
        .cte("barcode_page_parents").prefix_with("MATERIALIZED")
    entries, quantity = sizes_for(chosen, "barcode_page_sizes")
    raw_units = union_all(
        select(cast(entries.c.key, Text).label("size_name"), quantity.label("size_quantity"), literal(0).label("unallocated"))
        .select_from(entries).where(quantity != 0).correlate(chosen),
        select(literal(""), literal(0), literal(1)),
    ).subquery("barcode_local_units")
    allocated = select(
        raw_units.c.size_name, raw_units.c.unallocated,
        case((raw_units.c.unallocated == 1, chosen.c.parent_quantity - func.sum(raw_units.c.size_quantity).over()),
             else_=raw_units.c.size_quantity).label("quantity"),
        func.count().over().label("unit_count"),
    ).correlate(chosen).subquery("barcode_local_balances")
    units = select(allocated.c.size_name, allocated.c.unallocated, allocated.c.quantity)\
        .where(or_(allocated.c.unallocated == 0, allocated.c.quantity != 0, allocated.c.unit_count == 1,
                   and_(chosen.c.parent_quantity == 0, chosen.c.parent_amount != 0)))\
        .correlate(chosen).subquery("barcode_page_units")
    cumulative = func.sum(units.c.quantity).over(order_by=(units.c.unallocated, units.c.size_name), rows=(None, 0))
    divisor = func.nullif(chosen.c.parent_quantity, 0)
    amount = case(
        (chosen.c.parent_quantity == 0, case((units.c.unallocated == 1, chosen.c.parent_amount), else_=0)),
        else_=(func.round(chosen.c.parent_amount * cumulative / divisor, 2)
               - func.round(chosen.c.parent_amount * (cumulative - units.c.quantity) / divisor, 2)),
    )
    local_lines = select(units, amount.label("amount")).correlate(chosen).lateral("barcode_local_lines")
    paged = select(
        chosen.c.detail_id, chosen.c.date_value, chosen.c.date, chosen.c.document_number,
        local_lines.c.size_name, local_lines.c.unallocated, local_lines.c.quantity, local_lines.c.amount,
    ).select_from(chosen.join(local_lines, true()))\
        .order_by(*parent_order(chosen.c), local_lines.c.unallocated, local_lines.c.size_name)\
        .offset(offset).limit(page_size).cte("barcode_page").prefix_with("MATERIALIZED")
    source = totals.outerjoin(paged, true()).outerjoin(detail, detail.c.id == paged.c.detail_id)\
        .outerjoin(record, record.c.id == detail.c.document_id)
    return select(
        detail.c.id, detail.c.document_id, detail.c.product_identity_id, detail.c.product_code,
        detail.c.product_name, detail.c.color_name, detail.c.color_spec, detail.c.unit_price,
        paged.c.size_name, paged.c.unallocated, paged.c.quantity, paged.c.amount,
        record.c.document_type, record.c.document_number, record.c.date, record.c.supplier, record.c.warehouse,
        totals.c.detail_count, totals.c.quantity_total, totals.c.amount_total,
    ).select_from(source).order_by(*parent_order(paged.c), paged.c.unallocated, paged.c.size_name)


def _load_profiles(connection, rows):
    """Resolve only current-page archives, preferring the saved product identity."""
    identity_ids = {row["product_identity_id"] for row in rows if row["product_identity_id"] is not None}
    identities = {}
    if identity_ids:
        identities = {row["id"]: dict(row) for row in connection.execute(
            select(PRODUCT_ARCHIVE_IDENTITY_TABLE).where(PRODUCT_ARCHIVE_IDENTITY_TABLE.c.id.in_(identity_ids)),
        ).mappings()}
    codes = {_text(row["product_code"]) for row in rows if row["product_identity_id"] is None and _text(row["product_code"])}
    tables = {table.name: table for table in PRODUCT_ARCHIVE_TABLES.values()}
    configured = connection.execute(select(SUPPLIER_BRAND_TABLE.c.product_table_name).where(
        SUPPLIER_BRAND_TABLE.c.product_archive_enabled.is_(True),
    )).scalars()
    for name in configured:
        name = _text(name)
        if manual_product_table_name(name):
            tables[name] = build_product_archive_table(name, metadata=MetaData())
    linked = defaultdict(set)
    for identity in identities.values():
        if identity["is_active"]:
            linked[identity["source_table"]].add(identity["source_product_id"])
    profiles, exact, aliases = {}, defaultdict(list), defaultdict(list)
    statements = []
    for name, table in tables.items():
        conditions = []
        if linked[name]:
            conditions.append(table.c.id.in_(linked[name]))
        if codes:
            conditions.extend((table.c.sku.in_(codes), table.c.original_sku.in_(codes)))
        if not conditions:
            continue
        statements.append(select(
            literal(name).label("source_table"), table.c.id, table.c.sku, table.c.original_sku, table.c.color, table.c.color_code,
            table.c.size_range, table.c.barcode_build_rule,
        ).where(table.c.deleted_at.is_(None), or_(*conditions)))
    if statements:
        for raw in connection.execute(union_all(*statements)).mappings():
            profile = dict(raw)
            profiles[(profile["source_table"], profile["id"])] = profile
            if _text(profile["sku"]) in codes:
                exact[_text(profile["sku"])].append(profile)
            if _text(profile["original_sku"]) in codes:
                aliases[_text(profile["original_sku"])].append(profile)
    resolved = {}
    for row in rows:
        identity_id = row["product_identity_id"]
        if identity_id is not None:
            identity = identities.get(identity_id)
            profile = profiles.get((identity["source_table"], identity["source_product_id"])) if identity and identity["is_active"] else None
            resolved[row["id"]] = (profile, "商品档案已删除或关联不可用，请联系商品部维护")
            continue
        candidates = exact[_text(row["product_code"])] or aliases[_text(row["product_code"])]
        color = _text(row["color_name"] or row["color_spec"])
        if len(candidates) > 1 and color:
            candidates = [item for item in candidates if _text(item["color"]) == color]
        resolved[row["id"]] = (
            candidates[0] if len(candidates) == 1 else None,
            "商品档案匹配不唯一，请联系商品部维护" if len(candidates) > 1 else "未匹配商品档案，请联系商品部维护",
        )
    ranges = {_text(profile["size_range"]) for profile, _ in resolved.values() if profile and _text(profile["size_range"])}
    size_map = defaultdict(dict)
    if ranges:
        sizes = connection.execute(select(
            SIZE_GROUPS_TABLE.c.name, SIZE_GROUP_ITEMS_TABLE.c.size_name, SIZE_GROUP_ITEMS_TABLE.c.barcode,
        ).select_from(SIZE_GROUPS_TABLE.join(SIZE_GROUP_ITEMS_TABLE, SIZE_GROUP_ITEMS_TABLE.c.size_group_id == SIZE_GROUPS_TABLE.c.id))
          .where(SIZE_GROUPS_TABLE.c.name.in_(ranges))).mappings()
        for item in sizes:
            size_map[item["name"]][_text(item["size_name"])] = item
            size_map[item["name"]].setdefault(_text(item["barcode"]), item)
    return resolved, size_map


def list_detail_barcodes(repository, *, criterion, signed_quantity, signed_amount, return_type, is_sales,
                         sort_direction, page, page_size, size_name, quantity_field, amount_field, selected_rows=None):
    with repository.engine.connect() as connection:
        cache = getattr(repository, "_warehouse_inventory_cache", None)
        # The warehouse revision tracks inventory writes. Brand filters also
        # depend on supplier/configuration tables that it does not track, so
        # those queries always count afresh. Archives are never cached here.
        cacheable = (cache is not None and connection.dialect.name == "postgresql"
                     and not size_name and selected_rows is None
                     and all(getattr(node, "table", None) is None
                             or getattr(node, "table", None) is INVENTORY_TABLE
                             or getattr(node, "table", None) is INVENTORY_DETAIL_TABLE
                             for node in visitors.iterate(criterion)))
        filter_key = str(criterion.compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True})) if cacheable else ""
        version = repository._warehouse_inventory_version(connection) if cacheable and len(filter_key) <= 4096 else None
        key = ("barcode_detail_totals", version, return_type, is_sales, filter_key)
        result = None

        def query(cached_totals=None):
            statement = _barcode_statements(connection, criterion, signed_quantity, signed_amount, return_type, is_sales,
                                            sort_direction, page, page_size, size_name, selected_rows, cached_totals)
            return connection.execute(statement).mappings().all()

        if version is not None:
            def load_totals():
                nonlocal result
                result = query()
                if repository._warehouse_inventory_version(connection) != version:
                    result = None
                    return None
                return InventoryGroups.from_result({"items": [], "total": 0, "totals": {
                    "detail_count": int(result[0]["detail_count"]),
                    "quantity_total": str(result[0]["quantity_total"]),
                    "amount_total": str(result[0]["amount_total"]),
                }})

            groups = cache.get_or_load(key, load_totals)
            if result is None and groups is not None:
                result = query(groups.page(1, 1, False)["totals"])
                if repository._warehouse_inventory_version(connection) != version:
                    result = query()
        if result is None:
            result = query()
        totals = result[0]
        rows = [dict(row) for row in result if row["id"] is not None]
        profiles, sizes = {}, {}
        # Exports may contain up to 100000 expanded rows. Bound IN parameters
        # and archive lookup working sets just as for an ordinary page.
        for start in range(0, len(rows), 1000):
            batch_profiles, batch_sizes = _load_profiles(connection, rows[start:start + 1000])
            profiles.update(batch_profiles)
            for name, values in batch_sizes.items():
                sizes.setdefault(name, {}).update(values)
        suppliers = {_text(row["supplier"]) for row in rows if _text(row["supplier"])}
        supplier_codes = {}
        if suppliers and not is_sales:
            for item in connection.execute(select(SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.factory_code)
                                           .where(SUPPLIER_TABLE.c.name.in_(suppliers))).mappings():
                if item["factory_code"] or item["name"] not in supplier_codes:
                    supplier_codes[item["name"]] = item["factory_code"] or ""
    items = []
    fmt = repository._format_decimal
    for index, row in enumerate(rows, (page - 1) * page_size + 1):
        profile, issue = profiles[row["id"]]
        size = sizes.get(_text(profile["size_range"]), {}).get(_text(row["size_name"])) if profile else None
        color_code = _text(profile["color_code"]) if profile else ""
        barcode = ""
        if row["unallocated"]:
            issue = "尺码数量缺失或与明细数量不一致，请核对单据"
        elif profile:
            rule = _text(profile["barcode_build_rule"])
            if not _text(profile["sku"]):
                issue = "请联系商品部维护商品货号"
            elif rule not in {"货号+尺码", "货号+颜色代码+尺码"}:
                issue = "请联系商品部维护条码构成逻辑"
            elif rule == "货号+颜色代码+尺码" and not color_code:
                issue = "请联系商品部维护颜色条码"
            elif not size or not _text(size["barcode"]):
                issue = "请联系商品部维护尺码组及尺码条码"
            else:
                barcode = build_product_size_code(profile["sku"], color_code, size["barcode"], rule)
                issue = ""
        items.append({
            "row_number": index, "row_key": f"{row['id']}:{row['unallocated']}:{row['size_name']}",
            "detail_id": row["id"], "document_id": row["document_id"], "product_code": row["product_code"],
            "product_name": row["product_name"], "document_type": row["document_type"],
            "document_number": row["document_number"], "date": row["date"],
            quantity_field: fmt(row["quantity"]), amount_field: fmt(row["amount"]),
            "unit_price": fmt(row["unit_price"]) if row["unit_price"] is not None else None,
            "retail_amount": "", "factory_code": "", "unit_code": supplier_codes.get(_text(row["supplier"]), ""),
            "unit_name": row["supplier"], "warehouse_name": row["warehouse"],
            "color_name": row["color_name"] or row["color_spec"] or "", "barcode": barcode,
            "color_barcode": color_code, "size_name": size["size_name"] if size else row["size_name"],
            "size_barcode": _text(size["barcode"]) if size else "", "barcode_issue": issue,
        })
    all_totals = {quantity_field: fmt(totals["quantity_total"]), amount_field: fmt(totals["amount_total"]), "retail_amount": ""}
    page_totals = {field: fmt(sum((Decimal(item[field]) for item in items), Decimal(0))) for field in (quantity_field, amount_field)}
    page_totals["retail_amount"] = ""
    return {"items": items, "total": int(totals["detail_count"]), "page": page, "page_size": page_size,
            "totals": {**all_totals, "all": all_totals, "current_page": page_totals}}
