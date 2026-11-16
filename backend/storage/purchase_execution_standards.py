"""Read current archive remarks and defaults for old purchase lines in batches."""
from collections import defaultdict

from sqlalchemy import MetaData, inspect, or_, select

from domain.inventory_schema import SUPPLIER_BRAND_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from domain.product_archive_naming import manual_product_table_name
from domain.schema import PRODUCT_ARCHIVE_TABLES, build_product_archive_table


def enrich_purchase_execution_standards(repository, details):
    _enrich_purchase_archive_fields(repository, details, include_remarks=False)


def enrich_purchase_archive_fields(repository, details):
    _enrich_purchase_archive_fields(repository, details, include_remarks=True)


def enrich_purchase_product_remarks(repository, details):
    _enrich_purchase_archive_fields(repository, details, include_remarks=True, include_standards=False)


def _enrich_purchase_archive_fields(repository, details, *, include_remarks, include_standards=True):
    # An explicit value, including an intentionally cleared value, belongs to
    # the purchase line. Only older lines without this key need an archive default.
    pending = [detail for detail in details if include_remarks or "execution_standard" not in (detail.get("extra_fields") or {})]
    if include_remarks:
        # The archive is authoritative, even when cleared. Never display an old
        # line remark or borrow one from an ambiguous/unmatched product.
        for detail in pending:
            detail["remark"] = ""
    if not pending:
        return
    identity_ids = sorted({int(detail["product_identity_id"]) for detail in pending if detail.get("product_identity_id")})
    codes = sorted({str(detail.get("product_code") or "").strip() for detail in pending
                    if not detail.get("product_identity_id") and str(detail.get("product_code") or "").strip()})
    if not identity_ids and not codes:
        return
    with repository.engine.connect() as connection:
        inspector = inspect(connection)
        tables = {table.name: table for table in PRODUCT_ARCHIVE_TABLES.values()}
        if inspector.has_table(SUPPLIER_BRAND_TABLE.name):
            names = connection.execute(select(SUPPLIER_BRAND_TABLE.c.product_table_name)
                .where(SUPPLIER_BRAND_TABLE.c.product_archive_enabled.is_(True))).scalars()
            for value in names:
                name = manual_product_table_name(value)
                if name and name not in tables:
                    tables[name] = build_product_archive_table(name, metadata=MetaData())
        identities = {}
        identity = PRODUCT_ARCHIVE_IDENTITY_TABLE
        for offset in range(0, len(identity_ids), 1000):
            for row in connection.execute(select(identity.c.id, identity.c.source_table, identity.c.source_product_id)
                    .where(identity.c.id.in_(identity_ids[offset:offset + 1000]))).mappings():
                identities[row["id"]] = (row["source_table"], row["source_product_id"])
        by_table = defaultdict(set)
        for table_name, product_id in identities.values():
            by_table[table_name].add(product_id)
        profiles, exact, aliases = {}, defaultdict(set), defaultdict(set)
        code_set = set(codes)
        for name, table in tables.items():
            product_ids = sorted(by_table[name])
            if (not product_ids and not codes) or not inspector.has_table(name):
                continue
            for offset in range(0, max(len(product_ids), len(codes)), 1000):
                code_batch = codes[offset:offset + 1000]
                columns = [table.c.id, table.c.sku, table.c.original_sku]
                if include_standards:
                    columns.append(table.c.execution_standard)
                if include_remarks:
                    columns.append(table.c.remark)
                rows = connection.execute(select(*columns)
                    .where(table.c.deleted_at.is_(None), or_(table.c.id.in_(product_ids[offset:offset + 1000]),
                        table.c.sku.in_(code_batch), table.c.original_sku.in_(code_batch)))).mappings()
                for row in rows:
                    key = (name, row["id"])
                    profiles[key] = row
                    if row["sku"] in code_set:
                        exact[row["sku"]].add(key)
                    if row["original_sku"] in code_set:
                        aliases[row["original_sku"]].add(key)
        for detail in pending:
            if detail.get("product_identity_id"):
                key = identities.get(detail["product_identity_id"])
            else:
                code = str(detail.get("product_code") or "").strip()
                candidates = exact[code] or aliases[code]
                key = next(iter(candidates)) if len(candidates) == 1 else None
            if key in profiles:
                profile = profiles[key]
                if include_standards and "execution_standard" not in (detail.get("extra_fields") or {}):
                    detail["extra_fields"] = {**(detail.get("extra_fields") or {}), "execution_standard": str(profile["execution_standard"] or "").strip()}
                if include_remarks:
                    detail["remark"] = str(profile["remark"] or "").strip()
