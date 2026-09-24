from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Identity, Index, Table, Text, UniqueConstraint, inspect, text
from sqlalchemy.engine import Connection

from domain.schema import METADATA, PRODUCT_ARCHIVE_TABLES


PRODUCT_ARCHIVE_IDENTITY_TABLE = Table(
    "product_archive_identities",
    METADATA,
    Column("id", BigInteger, Identity(always=False), primary_key=True),
    Column("brand", Text, nullable=False),
    Column("source_table", Text, nullable=False),
    Column("source_product_id", BigInteger, nullable=False),
    Column("sku", Text, nullable=True),
    Column("original_sku", Text, nullable=True),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("date_trunc('minute', now())")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("date_trunc('minute', now())")),
    UniqueConstraint("source_table", "source_product_id", name="uq_product_archive_identity_source"),
)
Index("idx_product_archive_identities_brand_sku", PRODUCT_ARCHIVE_IDENTITY_TABLE.c.brand, PRODUCT_ARCHIVE_IDENTITY_TABLE.c.sku)
Index("idx_product_archive_identities_sku", PRODUCT_ARCHIVE_IDENTITY_TABLE.c.sku)
Index(
    "idx_product_archive_identities_brand_original_sku",
    PRODUCT_ARCHIVE_IDENTITY_TABLE.c.brand,
    PRODUCT_ARCHIVE_IDENTITY_TABLE.c.original_sku,
)


STATIC_PRODUCT_ARCHIVE_TABLE_BRANDS = {
    table.name: brand
    for brand, table in PRODUCT_ARCHIVE_TABLES.items()
}
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
HISTORY_PRODUCT_SYNC_FIELDS = ("color_code", "color", "size_range")
PURCHASE_PRODUCT_EXTRA_FIELD_MAPPING = {
    "factory_sku": "factory_code",
    "upper_material": "upper_material",
    "lining_material": "lining_material",
    "outsole_material": "outsole_material",
    "insole_material": "insole_material",
    "shoe_box_spec": "shoe_box_spec",
}
PURCHASE_PRODUCT_SYNC_FIELDS = (
    "sku", "original_sku", "product_name", "cost",
    *HISTORY_PRODUCT_SYNC_FIELDS,
    *PURCHASE_PRODUCT_EXTRA_FIELD_MAPPING,
)


def product_sync_fields_changed(before: Mapping, after: Mapping, fields: Iterable[str]) -> bool:
    return any(before.get(field) != after.get(field) for field in fields)


def _is_postgresql(connection: Connection) -> bool:
    return getattr(getattr(connection, "dialect", None), "name", None) == "postgresql"


def _identifier(value: object) -> str:
    name = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"Unsupported PostgreSQL identifier: {name!r}")
    return name


def _archive_table_specs(connection: Connection) -> list[tuple[str, str]]:
    specs = list(STATIC_PRODUCT_ARCHIVE_TABLE_BRANDS.items())
    if inspect(connection).has_table("supplier_brands"):
        rows = connection.execute(text("""
            SELECT lower(btrim(code)) AS brand, btrim(product_table_name) AS table_name
            FROM supplier_brands
            WHERE product_archive_enabled = TRUE
              AND product_table_name ~ '^manual_product_archive_[0-9]+$'
        """)).mappings()
        specs.extend((str(row["table_name"]), str(row["brand"])) for row in rows)
    return list(dict.fromkeys(specs))


def _install_functions(connection: Connection) -> None:
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION hede_replace_purchase_product_cache(
            payload json,
            old_sku text,
            new_sku text,
            old_original_sku text,
            new_original_sku text
        ) RETURNS json
        LANGUAGE plpgsql
        AS $$
        DECLARE
            result jsonb := COALESCE(payload::jsonb, '{}'::jsonb);
            cache_key text;
            cache_value text;
            replacement text;
        BEGIN
            FOREACH cache_key IN ARRAY ARRAY['image_code', 'style_code'] LOOP
                cache_value := btrim(COALESCE(result ->> cache_key, ''));
                replacement := NULL;
                IF cache_value <> '' AND cache_value = btrim(COALESCE(old_sku, '')) THEN
                    replacement := btrim(COALESCE(new_sku, ''));
                ELSIF cache_value <> '' AND cache_value = btrim(COALESCE(old_original_sku, '')) THEN
                    replacement := btrim(COALESCE(new_original_sku, ''));
                END IF;
                IF replacement IS NOT NULL THEN
                    result := jsonb_set(result, ARRAY[cache_key], to_jsonb(replacement), true);
                END IF;
            END LOOP;
            RETURN result::json;
        END;
        $$
    """))
    sync_fields_sql = ", ".join(f"'{field}'" for field in PURCHASE_PRODUCT_SYNC_FIELDS)
    extra_fields_sql = ", ".join(
        f"('{source}', '{target}')"
        for source, target in PURCHASE_PRODUCT_EXTRA_FIELD_MAPPING.items()
    )
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION hede_sync_product_archive_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            archive_brand text := lower(btrim(TG_ARGV[0]));
            identity_id bigint;
            current_sku text;
            old_product jsonb;
            new_product jsonb;
            changed_fields jsonb;
            history_extra jsonb := '{}'::jsonb;
            purchase_extra jsonb := '{}'::jsonb;
            history_changed boolean;
            size_labels text;
            source_field text;
            target_field text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                UPDATE product_archive_identities
                SET is_active = false,
                    updated_at = date_trunc('minute', now())
                WHERE source_table = TG_TABLE_NAME
                  AND source_product_id = OLD.id;
                RETURN OLD;
            END IF;

            current_sku := COALESCE(NULLIF(btrim(NEW.sku), ''), NULLIF(btrim(NEW.original_sku), ''));
            INSERT INTO product_archive_identities (
                brand,
                source_table,
                source_product_id,
                sku,
                original_sku,
                is_active,
                updated_at
            ) VALUES (
                archive_brand,
                TG_TABLE_NAME,
                NEW.id,
                NULLIF(btrim(NEW.sku), ''),
                NULLIF(btrim(NEW.original_sku), ''),
                NEW.deleted_at IS NULL,
                date_trunc('minute', now())
            )
            ON CONFLICT (source_table, source_product_id) DO UPDATE
            SET brand = EXCLUDED.brand,
                sku = EXCLUDED.sku,
                original_sku = EXCLUDED.original_sku,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.updated_at
            RETURNING id INTO identity_id;

            IF TG_OP = 'UPDATE' THEN
                old_product := to_jsonb(OLD);
                new_product := to_jsonb(NEW);
                SELECT COALESCE(jsonb_object_agg(key, value), '{}'::jsonb)
                INTO changed_fields
                FROM jsonb_each(new_product)
                WHERE key IN (__SYNC_FIELDS__)
                  AND value IS DISTINCT FROM old_product -> key;
                IF changed_fields = '{}'::jsonb THEN
                    RETURN NEW;
                END IF;

                history_changed := changed_fields ?| ARRAY['color_code', 'color', 'size_range'];
                IF changed_fields ? 'size_range' THEN
                    IF to_regclass('size_groups') IS NOT NULL AND to_regclass('size_group_items') IS NOT NULL THEN
                        SELECT string_agg(item.size_name, '|' ORDER BY item.sort_order, item.id)
                        INTO size_labels
                        FROM size_group_items AS item
                        JOIN size_groups AS size_group ON size_group.id = item.size_group_id
                        WHERE size_group.name = new_product ->> 'size_range';
                    END IF;
                    history_extra := jsonb_build_object(
                        'size_range', COALESCE(new_product ->> 'size_range', ''),
                        'size_labels', COALESCE(size_labels, '')
                    );
                END IF;
                purchase_extra := history_extra;
                FOR source_field, target_field IN
                    SELECT * FROM (VALUES __EXTRA_FIELDS__) AS mapping(source_field, target_field)
                LOOP
                    IF changed_fields ? source_field THEN
                        purchase_extra := purchase_extra || jsonb_build_object(
                            target_field, COALESCE(new_product ->> source_field, '')
                        );
                    END IF;
                END LOOP;

                UPDATE inventory_details AS detail
                SET product_code = CASE WHEN changed_fields ?| ARRAY['sku', 'original_sku']
                        THEN COALESCE(current_sku, detail.product_code) ELSE detail.product_code END,
                    product_name = CASE WHEN changed_fields ? 'product_name'
                        THEN new_product ->> 'product_name' ELSE detail.product_name END,
                    color_barcode = CASE WHEN changed_fields ? 'color_code'
                        THEN new_product ->> 'color_code' ELSE detail.color_barcode END,
                    color_name = CASE WHEN changed_fields ? 'color'
                        THEN new_product ->> 'color' ELSE detail.color_name END,
                    color_spec = CASE WHEN changed_fields ? 'color'
                        THEN new_product ->> 'color' ELSE detail.color_spec END,
                    unit_price = CASE WHEN changed_fields ? 'cost'
                        THEN (new_product ->> 'cost')::numeric ELSE detail.unit_price END,
                    amount = CASE WHEN changed_fields ? 'cost'
                        THEN round(COALESCE(detail.quantity, 0) * (new_product ->> 'cost')::numeric, 2)
                        ELSE detail.amount END,
                    extra_fields = ((CASE WHEN changed_fields ?| ARRAY['sku', 'original_sku']
                        THEN hede_replace_purchase_product_cache(
                            detail.extra_fields, OLD.sku, NEW.sku, OLD.original_sku, NEW.original_sku
                        )::jsonb
                        ELSE COALESCE(detail.extra_fields::jsonb, '{}'::jsonb)
                    END) || purchase_extra)::json,
                    updated_at = date_trunc('minute', now())
                FROM inventory_records AS record
                WHERE detail.document_id = record.id
                  AND record.document_type = '进货订单'
                  AND detail.product_identity_id = identity_id;

                IF history_changed THEN
                    UPDATE inventory_details AS detail
                    SET color_barcode = CASE WHEN changed_fields ? 'color_code'
                            THEN new_product ->> 'color_code' ELSE detail.color_barcode END,
                        color_name = CASE WHEN changed_fields ? 'color'
                            THEN new_product ->> 'color' ELSE detail.color_name END,
                        extra_fields = CASE WHEN changed_fields ? 'size_range'
                            THEN (COALESCE(detail.extra_fields::jsonb, '{}'::jsonb) || history_extra)::json
                            ELSE detail.extra_fields END,
                        updated_at = date_trunc('minute', now())
                    FROM inventory_records AS record
                    WHERE detail.document_id = record.id
                      AND record.document_type IS DISTINCT FROM '进货订单'
                      AND detail.product_identity_id = identity_id;
                END IF;

                UPDATE inventory_records AS record
                SET updated_at = date_trunc('minute', now())
                WHERE (record.document_type = '进货订单' OR history_changed)
                  AND EXISTS (
                      SELECT 1
                      FROM inventory_details AS detail
                      WHERE detail.document_id = record.id
                        AND detail.product_identity_id = identity_id
                  );
                IF changed_fields ? 'cost' THEN
                    UPDATE inventory_records AS record
                    SET amount = (
                        SELECT COALESCE(sum(detail.amount), 0)
                        FROM inventory_details AS detail WHERE detail.document_id = record.id
                    )
                    WHERE record.document_type = '进货订单'
                      AND EXISTS (
                          SELECT 1 FROM inventory_details AS detail
                          WHERE detail.document_id = record.id AND detail.product_identity_id = identity_id
                      );
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
    """.replace("__SYNC_FIELDS__", sync_fields_sql).replace("__EXTRA_FIELDS__", extra_fields_sql)))
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION hede_link_purchase_order_detail_product()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            record_type text;
            record_brand text;
            record_supplier text;
            identity_count integer;
            resolved_identity_id bigint;
            resolved_sku text;
        BEGIN
            SELECT
                btrim(COALESCE(document_type, '')),
                lower(btrim(COALESCE(raw_payload ->> 'brand', ''))),
                lower(btrim(COALESCE(supplier, '')))
            INTO record_type, record_brand, record_supplier
            FROM inventory_records
            WHERE id = NEW.document_id;

            IF NULLIF(btrim(NEW.product_code), '') IS NULL THEN
                NEW.product_identity_id := NULL;
                RETURN NEW;
            END IF;

            IF TG_OP = 'UPDATE'
               AND NEW.product_code IS DISTINCT FROM OLD.product_code
               AND NEW.product_identity_id IS NOT DISTINCT FROM OLD.product_identity_id THEN
                IF NOT EXISTS (
                    SELECT 1 FROM product_archive_identities
                    WHERE id = NEW.product_identity_id
                      AND NULLIF(btrim(NEW.product_code), '') IN (sku, original_sku)
                ) THEN
                    NEW.product_identity_id := NULL;
                END IF;
            END IF;

            IF NEW.product_identity_id IS NOT NULL THEN
                SELECT COALESCE(NULLIF(btrim(sku), ''), NULLIF(btrim(original_sku), ''))
                INTO resolved_sku
                FROM product_archive_identities
                WHERE id = NEW.product_identity_id;
                IF FOUND THEN
                    IF record_type = '进货订单' OR TG_OP = 'INSERT'
                       OR NEW.product_identity_id IS DISTINCT FROM OLD.product_identity_id
                       OR NEW.product_code IS DISTINCT FROM OLD.product_code THEN
                        NEW.product_code := COALESCE(NULLIF(btrim(resolved_sku), ''), NEW.product_code);
                    END IF;
                    RETURN NEW;
                END IF;
                NEW.product_identity_id := NULL;
            END IF;

            IF record_brand = '' AND record_supplier <> ''
               AND record_type IN ('进货订单', '进货单', '进货退货单') THEN
                SELECT CASE
                    WHEN count(DISTINCT lower(btrim(brand))) = 1
                    THEN min(lower(btrim(brand)))
                    ELSE ''
                END
                INTO record_brand
                FROM suppliers
                WHERE lower(btrim(name)) = record_supplier;
            END IF;

            IF NULLIF(btrim(NEW.product_code), '') IS NULL THEN
                RETURN NEW;
            END IF;

            IF record_brand <> '' THEN
                SELECT count(*), min(id), min(sku)
                INTO identity_count, resolved_identity_id, resolved_sku
                FROM product_archive_identities
                WHERE brand = record_brand
                  AND is_active = true
                  AND sku = NULLIF(btrim(NEW.product_code), '');

                IF identity_count = 0 THEN
                    SELECT count(*), min(id), min(sku)
                    INTO identity_count, resolved_identity_id, resolved_sku
                    FROM product_archive_identities
                    WHERE brand = record_brand
                      AND is_active = true
                      AND original_sku = NULLIF(btrim(NEW.product_code), '');
                END IF;
                IF identity_count > 1 THEN
                    SELECT count(*), min(id), min(sku)
                    INTO identity_count, resolved_identity_id, resolved_sku
                    FROM product_archive_identities
                    WHERE brand = record_brand
                      AND is_active = true
                      AND original_sku = NULLIF(btrim(NEW.product_code), '')
                      AND (
                          btrim(COALESCE(NEW.product_name, '')) LIKE sku || '%'
                          OR (
                              NULLIF(btrim(COALESCE(NEW.color_barcode, '')), '') IS NOT NULL
                              AND sku LIKE '%' || btrim(NEW.color_barcode)
                          )
                      );
                END IF;
            ELSE
                SELECT count(*), min(id), min(sku)
                INTO identity_count, resolved_identity_id, resolved_sku
                FROM product_archive_identities
                WHERE is_active = true
                  AND sku = NULLIF(btrim(NEW.product_code), '');
            END IF;

            IF identity_count = 1 THEN
                NEW.product_identity_id := resolved_identity_id;
                NEW.product_code := COALESCE(NULLIF(btrim(resolved_sku), ''), NEW.product_code);
            END IF;
            RETURN NEW;
        END;
        $$
    """))
    install_document_product_link_function(connection)


def install_document_product_link_function(connection: Connection) -> None:
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION hede_refresh_document_product_links()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.document_type IS DISTINCT FROM OLD.document_type
               OR NEW.supplier IS DISTINCT FROM OLD.supplier
               OR NEW.raw_payload::jsonb IS DISTINCT FROM OLD.raw_payload::jsonb THEN
                UPDATE inventory_details
                SET product_identity_id = CASE
                        WHEN NEW.document_type IS NOT DISTINCT FROM OLD.document_type
                         AND NEW.supplier IS NOT DISTINCT FROM OLD.supplier
                         AND (NEW.raw_payload::jsonb ->> 'brand') IS NOT DISTINCT FROM (OLD.raw_payload::jsonb ->> 'brand')
                        THEN product_identity_id ELSE NULL END,
                    product_code = product_code
                WHERE document_id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$
    """))


def _ensure_trigger(
    connection: Connection,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    trigger_type: int,
    columns: tuple[str, ...],
    arguments: tuple[str, ...] = (),
    definition: str,
) -> None:
    table_name = _identifier(table_name)
    trigger_name = _identifier(trigger_name)
    function_name = _identifier(function_name)
    existing = connection.execute(text("""
        SELECT trigger.tgtype, trigger.tgenabled, trigger.tgargs,
            trigger.tgqual IS NULL AS unconditional,
            trigger.tgconstraint = 0 AS ordinary,
            trigger.tgoldtable IS NULL AND trigger.tgnewtable IS NULL AS no_transition_tables,
            trigger.tgfoid = to_regprocedure(format('%I.%I()', current_schema(), CAST(:function_name AS text))) AS function_matches,
            ARRAY(
                SELECT attribute.attname::text
                FROM unnest(trigger.tgattr::smallint[]) AS updated_column(attnum)
                JOIN pg_catalog.pg_attribute attribute
                    ON attribute.attrelid = trigger.tgrelid
                    AND attribute.attnum = updated_column.attnum
                ORDER BY attribute.attname
            ) AS updated_columns
        FROM pg_catalog.pg_trigger trigger
        WHERE trigger.tgrelid = to_regclass(:table_name)
            AND trigger.tgname = :trigger_name
            AND NOT trigger.tgisinternal
    """), {
        "table_name": table_name,
        "trigger_name": trigger_name,
        "function_name": function_name,
    }).mappings().first()
    expected_arguments = b"".join(value.encode("utf-8") + b"\0" for value in arguments)
    if existing is not None and (
        existing["tgtype"] == trigger_type
        and existing["tgenabled"] == "O"
        and bytes(existing["tgargs"]) == expected_arguments
        and existing["unconditional"]
        and existing["ordinary"]
        and existing["no_transition_tables"]
        and existing["function_matches"]
        and list(existing["updated_columns"]) == sorted(columns)
    ):
        return
    if existing is not None:
        connection.execute(text(f"DROP TRIGGER {trigger_name} ON {table_name}"))
    connection.execute(text(definition))


def _sync_archive_table(connection: Connection, table_name: str, brand: str) -> None:
    table_name = _identifier(table_name)
    brand = str(brand or "").strip().lower()
    if not brand:
        raise ValueError("Product archive brand cannot be empty")
    brand_literal = brand.replace("'", "''")
    if not inspect(connection).has_table(table_name):
        return
    connection.execute(text(f"""
        INSERT INTO product_archive_identities (
            brand,
            source_table,
            source_product_id,
            sku,
            original_sku,
            is_active,
            updated_at
        )
        SELECT
            :brand,
            :source_table,
            id,
            NULLIF(btrim(sku), ''),
            NULLIF(btrim(original_sku), ''),
            deleted_at IS NULL,
            date_trunc('minute', now())
        FROM {table_name}
        ON CONFLICT (source_table, source_product_id) DO UPDATE
        SET brand = EXCLUDED.brand,
            sku = EXCLUDED.sku,
            original_sku = EXCLUDED.original_sku,
            is_active = EXCLUDED.is_active,
            updated_at = EXCLUDED.updated_at
        WHERE product_archive_identities.brand IS DISTINCT FROM EXCLUDED.brand
           OR product_archive_identities.sku IS DISTINCT FROM EXCLUDED.sku
           OR product_archive_identities.original_sku IS DISTINCT FROM EXCLUDED.original_sku
           OR product_archive_identities.is_active IS DISTINCT FROM EXCLUDED.is_active
    """), {"brand": brand, "source_table": table_name})
    _ensure_trigger(
        connection,
        table_name=table_name,
        trigger_name="trg_hede_product_identity_sync",
        function_name="hede_sync_product_archive_identity",
        trigger_type=29,
        columns=(),
        arguments=(brand,),
        definition=f"""
        CREATE TRIGGER trg_hede_product_identity_sync
        AFTER INSERT OR DELETE OR UPDATE ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION hede_sync_product_archive_identity('{brand_literal}')
        """,
    )


def _backfill_inventory_product_details(connection: Connection) -> None:
    connection.execute(text("""
        WITH purchase_details AS MATERIALIZED (
            SELECT
                detail.id AS detail_id,
                btrim(COALESCE(detail.product_code, '')) AS product_code,
                COALESCE(
                    NULLIF(lower(btrim(COALESCE(record.raw_payload ->> 'brand', ''))), ''),
                    (
                        SELECT CASE
                            WHEN count(DISTINCT lower(btrim(supplier.brand))) = 1
                            THEN min(lower(btrim(supplier.brand)))
                            ELSE NULL
                        END
                        FROM suppliers AS supplier
                        WHERE record.document_type IN ('进货订单', '进货单', '进货退货单')
                          AND lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                    )
                ) AS brand
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE detail.product_identity_id IS NULL
              AND NULLIF(btrim(detail.product_code), '') IS NOT NULL
        ), matches AS (
            SELECT
                purchase_details.detail_id,
                min(identity.id) AS identity_id,
                min(identity.sku) AS sku,
                count(*) AS match_count
            FROM purchase_details
            JOIN product_archive_identities AS identity
              ON identity.is_active = true
             AND identity.brand = purchase_details.brand
             AND identity.sku = purchase_details.product_code
            WHERE purchase_details.brand IS NOT NULL
            GROUP BY purchase_details.detail_id
        )
        UPDATE inventory_details AS detail
        SET product_identity_id = matches.identity_id,
            product_code = COALESCE(NULLIF(btrim(matches.sku), ''), detail.product_code),
            updated_at = date_trunc('minute', now())
        FROM matches
        WHERE detail.id = matches.detail_id
          AND matches.match_count = 1
    """))
    connection.execute(text("""
        WITH purchase_details AS MATERIALIZED (
            SELECT
                detail.id AS detail_id,
                btrim(detail.product_code) AS product_code,
                btrim(COALESCE(detail.product_name, '')) AS product_name,
                btrim(COALESCE(detail.color_barcode, '')) AS color_barcode,
                COALESCE(
                    NULLIF(lower(btrim(COALESCE(record.raw_payload ->> 'brand', ''))), ''),
                    (
                        SELECT CASE
                            WHEN count(DISTINCT lower(btrim(supplier.brand))) = 1
                            THEN min(lower(btrim(supplier.brand)))
                            ELSE NULL
                        END
                        FROM suppliers AS supplier
                        WHERE record.document_type IN ('进货订单', '进货单', '进货退货单')
                          AND lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                    )
                ) AS brand
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE detail.product_identity_id IS NULL
              AND NULLIF(btrim(detail.product_code), '') IS NOT NULL
        ), matches AS (
            SELECT
                purchase_details.detail_id,
                min(identity.id) AS identity_id,
                min(identity.sku) AS sku,
                count(*) AS match_count
            FROM purchase_details
            JOIN product_archive_identities AS identity
              ON identity.is_active = true
             AND identity.brand = purchase_details.brand
             AND identity.original_sku = purchase_details.product_code
             AND (
                 purchase_details.product_name LIKE identity.sku || '%'
                 OR (
                     purchase_details.color_barcode <> ''
                     AND identity.sku LIKE '%' || purchase_details.color_barcode
                 )
             )
            WHERE purchase_details.brand IS NOT NULL
            GROUP BY purchase_details.detail_id
        )
        UPDATE inventory_details AS detail
        SET product_identity_id = matches.identity_id,
            product_code = COALESCE(NULLIF(btrim(matches.sku), ''), detail.product_code),
            updated_at = date_trunc('minute', now())
        FROM matches
        WHERE detail.id = matches.detail_id
          AND matches.match_count = 1
    """))
    connection.execute(text("""
        WITH purchase_details AS MATERIALIZED (
            SELECT
                detail.id AS detail_id,
                btrim(detail.product_code) AS product_code,
                COALESCE(
                    NULLIF(lower(btrim(COALESCE(record.raw_payload ->> 'brand', ''))), ''),
                    (
                        SELECT CASE
                            WHEN count(DISTINCT lower(btrim(supplier.brand))) = 1
                            THEN min(lower(btrim(supplier.brand)))
                            ELSE NULL
                        END
                        FROM suppliers AS supplier
                        WHERE record.document_type IN ('进货订单', '进货单', '进货退货单')
                          AND lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                    )
                ) AS brand
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE detail.product_identity_id IS NULL
              AND NULLIF(btrim(detail.product_code), '') IS NOT NULL
        ), matches AS (
            SELECT
                purchase_details.detail_id,
                min(identity.id) AS identity_id,
                min(identity.sku) AS sku,
                count(*) AS match_count
            FROM purchase_details
            JOIN product_archive_identities AS identity
              ON identity.is_active = true
             AND identity.brand = purchase_details.brand
             AND identity.original_sku = purchase_details.product_code
            WHERE purchase_details.brand IS NOT NULL
            GROUP BY purchase_details.detail_id
        )
        UPDATE inventory_details AS detail
        SET product_identity_id = matches.identity_id,
            product_code = COALESCE(NULLIF(btrim(matches.sku), ''), detail.product_code),
            updated_at = date_trunc('minute', now())
        FROM matches
        WHERE detail.id = matches.detail_id
          AND matches.match_count = 1
    """))
    connection.execute(text("""
        WITH purchase_details AS MATERIALIZED (
            SELECT detail.id AS detail_id, btrim(detail.product_code) AS product_code
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE detail.product_identity_id IS NULL
              AND NULLIF(btrim(detail.product_code), '') IS NOT NULL
              AND NULLIF(lower(btrim(COALESCE(record.raw_payload ->> 'brand', ''))), '') IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM suppliers AS supplier
                  WHERE record.document_type IN ('进货订单', '进货单', '进货退货单')
                    AND lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                  HAVING count(DISTINCT NULLIF(lower(btrim(supplier.brand)), '')) = 1
              )
        ), matches AS (
            SELECT
                purchase_details.detail_id,
                min(identity.id) AS identity_id,
                min(identity.sku) AS sku,
                count(*) AS match_count
            FROM purchase_details
            JOIN product_archive_identities AS identity
              ON identity.is_active = true
             AND identity.sku = purchase_details.product_code
            GROUP BY purchase_details.detail_id
        )
        UPDATE inventory_details AS detail
        SET product_identity_id = matches.identity_id,
            product_code = COALESCE(NULLIF(btrim(matches.sku), ''), detail.product_code),
            updated_at = date_trunc('minute', now())
        FROM matches
        WHERE detail.id = matches.detail_id
          AND matches.match_count = 1
    """))


def _install_inventory_product_link_triggers(connection: Connection) -> None:
    _ensure_trigger(
        connection,
        table_name="inventory_details",
        trigger_name="trg_hede_purchase_detail_product_link",
        function_name="hede_link_purchase_order_detail_product",
        trigger_type=23,
        columns=("product_code", "product_identity_id", "document_id"),
        definition="""
        CREATE TRIGGER trg_hede_purchase_detail_product_link
        BEFORE INSERT OR UPDATE OF product_code, product_identity_id, document_id
        ON inventory_details
        FOR EACH ROW
        EXECUTE FUNCTION hede_link_purchase_order_detail_product()
        """,
    )
    _ensure_trigger(
        connection,
        table_name="inventory_records",
        trigger_name="trg_hede_inventory_record_product_links",
        function_name="hede_refresh_document_product_links",
        trigger_type=17,
        columns=("document_type", "supplier", "raw_payload"),
        definition="""
        CREATE TRIGGER trg_hede_inventory_record_product_links
        AFTER UPDATE OF document_type, supplier, raw_payload
        ON inventory_records
        FOR EACH ROW
        EXECUTE FUNCTION hede_refresh_document_product_links()
        """,
    )


def ensure_product_archive_identity_schema(
    connection: Connection,
    *,
    table_specs: Iterable[tuple[str, str]] | None = None,
) -> None:
    if not _is_postgresql(connection):
        return

    PRODUCT_ARCHIVE_IDENTITY_TABLE.create(connection, checkfirst=True)
    inspector = inspect(connection)
    if not (
        inspector.has_table("inventory_records")
        and inspector.has_table("inventory_details")
    ):
        # ProductRepository is initialized before InventoryRepository on a new
        # database. The inventory repository will finish this installation as
        # soon as both inventory tables exist.
        return

    if not any(column["name"] == "product_identity_id" for column in inspector.get_columns("inventory_details")):
        connection.execute(text(
            "ALTER TABLE inventory_details ADD COLUMN product_identity_id BIGINT"
        ))
    connection.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_inventory_details_product_identity'
                  AND conrelid = to_regclass('inventory_details')
            ) THEN
                ALTER TABLE inventory_details
                ADD CONSTRAINT fk_inventory_details_product_identity
                FOREIGN KEY (product_identity_id)
                REFERENCES product_archive_identities(id)
                ON DELETE SET NULL;
            END IF;
        END $$
    """))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_inventory_details_product_identity "
        "ON inventory_details (product_identity_id)"
    ))
    connection.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_product_archive_identities_sku "
        "ON product_archive_identities (sku)"
    ))
    _install_functions(connection)

    specs = list(table_specs) if table_specs is not None else _archive_table_specs(connection)
    for table_name, brand in specs:
        _sync_archive_table(connection, table_name, str(brand).strip().lower())

    _install_inventory_product_link_triggers(connection)
    connection.execute(text("""
        UPDATE inventory_details AS detail
        SET product_identity_id = NULL
        WHERE NULLIF(btrim(detail.product_code), '') IS NULL
          AND detail.product_identity_id IS NOT NULL
    """))
    _backfill_inventory_product_details(connection)


def product_archive_identity_coverage(connection: Connection) -> Mapping[str, int]:
    row = connection.execute(text("""
        SELECT
            count(*) FILTER (
                WHERE NULLIF(btrim(detail.product_code), '') IS NOT NULL
            ) AS product_details,
            count(*) FILTER (
                WHERE detail.product_identity_id IS NOT NULL
            ) AS linked_product_details,
            count(*) FILTER (
                WHERE NULLIF(btrim(detail.product_code), '') IS NOT NULL
                  AND detail.product_identity_id IS NULL
            ) AS unlinked_product_details,
            count(*) FILTER (WHERE record.document_type = '进货订单') AS purchase_details,
            count(*) FILTER (
                WHERE record.document_type = '进货订单'
                  AND detail.product_identity_id IS NOT NULL
            ) AS linked_purchase_details,
            count(*) FILTER (
                WHERE record.document_type <> '进货订单'
                  AND detail.product_identity_id IS NOT NULL
            ) AS linked_non_purchase_details
        FROM inventory_details AS detail
        JOIN inventory_records AS record ON record.id = detail.document_id
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}
