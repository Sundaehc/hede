"""Allocate and explicitly migrate readable manual product archive table names."""
from __future__ import annotations

import re

from sqlalchemy import inspect, text

from domain.product_archive_naming import LEGACY_ARCHIVE_PATTERN, manual_product_table_name, readable_product_table_name
from domain.schema import PRODUCT_ARCHIVE_TABLES


def allocate_product_table_name(connection, name: str, brand_id: int) -> str:
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(68473104)"))
    inspector = inspect(connection)
    occupied = set(inspector.get_table_names()) | set(inspector.get_view_names())
    if connection.dialect.name == "postgresql":
        occupied.update(connection.execute(text(
            "SELECT relname FROM pg_class WHERE relnamespace = current_schema()::regnamespace"
        )).scalars())
    occupied.update(table.name for table in PRODUCT_ARCHIVE_TABLES.values())
    occupied.update(connection.execute(text(
        "SELECT product_table_name FROM supplier_brands WHERE product_table_name IS NOT NULL"
    )).scalars())
    return readable_product_table_name(name, brand_id, occupied)


def archive_table_rename_plan(connection, *, downgrade: bool = False) -> list[dict]:
    """Plan using configured brands, never guessed table names or brand codes."""
    if not inspect(connection).has_table("supplier_brands"):
        return []
    occupied = set(inspect(connection).get_table_names()) | set(inspect(connection).get_view_names())
    if connection.dialect.name == "postgresql":
        occupied.update(connection.execute(text(
            "SELECT relname FROM pg_class WHERE relnamespace = current_schema()::regnamespace"
        )).scalars())
    brands = connection.execute(text(
        "SELECT id, code, name, product_table_name FROM supplier_brands ORDER BY id"
    )).mappings().all()
    occupied.update(row["product_table_name"] for row in brands if row["product_table_name"])
    occupied.update(table.name for table in PRODUCT_ARCHIVE_TABLES.values())
    plan = []
    for row in brands:
        old = manual_product_table_name(row["product_table_name"])
        if row["code"] in PRODUCT_ARCHIVE_TABLES or not old:
            continue
        legacy = bool(re.fullmatch(LEGACY_ARCHIVE_PATTERN, old, flags=re.ASCII))
        if legacy == downgrade:
            continue
        if not inspect(connection).has_table(old):
            raise ValueError(f"Configured product archive table is missing: {old}")
        if downgrade:
            new = f"manual_product_archive_{row['id']}"
            if new in occupied:
                raise ValueError(f"Cannot restore product archive name; target exists: {new}")
        else:
            new = readable_product_table_name(row["name"], row["id"], occupied)
        occupied.add(new)
        plan.append({"brand_id": row["id"], "brand_code": row["code"], "brand_name": row["name"], "old": old, "new": new})
    return plan


def rename_product_archive_tables(connection, *, downgrade: bool = False) -> list[dict]:
    """Rename in the caller's transaction, preserving product and identity IDs."""
    if connection.dialect.name != "postgresql":
        raise ValueError("Product archive table renaming requires PostgreSQL")
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '30s'"))
    connection.execute(text("SELECT pg_advisory_xact_lock(68473104)"))
    plan = archive_table_rename_plan(connection, downgrade=downgrade)
    quote = connection.dialect.identifier_preparer.quote_identifier
    # Acquire all table locks before changing any metadata. A timeout rolls back everything.
    for item in plan:
        connection.exec_driver_sql(f"LOCK TABLE {quote(item['old'])} IN ACCESS EXCLUSIVE MODE")
    inspector = inspect(connection)
    for item in plan:
        old, new = item["old"], item["new"]
        constraints = connection.execute(text(
            "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass(:name)"
        ), {"name": old}).scalars().all()
        indexes = connection.execute(text(
            "SELECT index_relation.relname FROM pg_index AS index_info "
            "JOIN pg_class index_relation ON index_relation.oid = index_info.indexrelid "
            "WHERE index_info.indrelid = to_regclass(:name)"
        ), {"name": old}).scalars().all()
        sequence = connection.scalar(text("SELECT pg_get_serial_sequence(:name, 'id')"), {"name": old})
        if inspector.has_table("product_archive_identities"):
            if connection.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM product_archive_identities WHERE source_table = :name)"
            ), {"name": new}):
                raise ValueError(f"Target archive name already has product identities: {new}")
        connection.exec_driver_sql(f"ALTER TABLE {quote(old)} RENAME TO {quote(new)}")
        # Constraint renaming also renames its backing index. Rename other indexes
        # so startup does not create duplicates under the new table name.
        renamed_indexes = set()
        for constraint in constraints:
            if old in constraint:
                target = constraint.replace(old, new)
                if len(target) > 63:
                    raise ValueError(f"Archive constraint name is too long: {target}")
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote(new)} RENAME CONSTRAINT {quote(constraint)} TO {quote(target)}"
                )
                renamed_indexes.add(constraint)
        for index in indexes:
            if old in index and index not in renamed_indexes:
                target = index.replace(old, new)
                if len(target) > 63:
                    raise ValueError(f"Archive index name is too long: {target}")
                connection.exec_driver_sql(f"ALTER INDEX {quote(index)} RENAME TO {quote(target)}")
        if sequence:
            sequence_name = sequence.rsplit('.', 1)[-1].strip('"')
            if old in sequence_name:
                connection.exec_driver_sql(
                    f"ALTER SEQUENCE {quote(sequence_name)} RENAME TO {quote(sequence_name.replace(old, new))}"
                )
        connection.execute(text(
            "UPDATE supplier_brands SET product_table_name = :new WHERE id = :brand_id"
        ), {"new": new, "brand_id": item["brand_id"]})
        if inspector.has_table("product_archive_identities"):
            connection.execute(text(
                "UPDATE product_archive_identities SET source_table = :new WHERE source_table = :old"
            ), {"new": new, "old": old})
        if inspector.has_table("data_quality_issues"):
            connection.execute(text(
                "UPDATE data_quality_issues SET table_name = :new WHERE table_name = :old"
            ), {"new": new, "old": old})
        comment = (item["brand_name"] + "商品信息档案").replace("'", "''")
        connection.exec_driver_sql(f"COMMENT ON TABLE {quote(new)} IS '{comment}'")
    return plan
