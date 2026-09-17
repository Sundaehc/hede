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
                    replacement := NULLIF(btrim(COALESCE(new_sku, '')), '');
                ELSIF cache_value <> '' AND cache_value = btrim(COALESCE(old_original_sku, '')) THEN
                    replacement := NULLIF(btrim(COALESCE(new_original_sku, '')), '');
                END IF;
                IF replacement IS NOT NULL THEN
                    result := jsonb_set(result, ARRAY[cache_key], to_jsonb(replacement), true);
                END IF;
            END LOOP;
            RETURN result::json;
        END;
        $$
    """))
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION hede_sync_product_archive_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            archive_brand text := lower(btrim(TG_ARGV[0]));
            identity_id bigint;
            current_sku text;
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

            IF TG_OP = 'UPDATE' AND (
                NEW.sku IS DISTINCT FROM OLD.sku
                OR NEW.original_sku IS DISTINCT FROM OLD.original_sku
            ) THEN
                UPDATE inventory_details AS detail
                SET product_code = COALESCE(current_sku, detail.product_code),
                    extra_fields = hede_replace_purchase_product_cache(
                        detail.extra_fields,
                        OLD.sku,
                        NEW.sku,
                        OLD.original_sku,
                        NEW.original_sku
                    ),
                    updated_at = date_trunc('minute', now())
                FROM inventory_records AS record
                WHERE detail.document_id = record.id
                  AND record.document_type = '进货订单'
                  AND detail.product_identity_id = identity_id;

                UPDATE inventory_records AS record
                SET updated_at = date_trunc('minute', now())
                WHERE record.document_type = '进货订单'
                  AND EXISTS (
                      SELECT 1
                      FROM inventory_details AS detail
                      WHERE detail.document_id = record.id
                        AND detail.product_identity_id = identity_id
                  );
            END IF;
            RETURN NEW;
        END;
        $$
    """))
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

            IF record_type IS DISTINCT FROM '进货订单' THEN
                NEW.product_identity_id := NULL;
                RETURN NEW;
            END IF;

            IF TG_OP = 'UPDATE'
               AND NEW.product_code IS DISTINCT FROM OLD.product_code
               AND NEW.product_identity_id IS NOT DISTINCT FROM OLD.product_identity_id THEN
                NEW.product_identity_id := NULL;
            END IF;

            IF NEW.product_identity_id IS NOT NULL THEN
                SELECT sku
                INTO resolved_sku
                FROM product_archive_identities
                WHERE id = NEW.product_identity_id;
                IF FOUND THEN
                    NEW.product_code := COALESCE(NULLIF(btrim(resolved_sku), ''), NEW.product_code);
                    RETURN NEW;
                END IF;
                NEW.product_identity_id := NULL;
            END IF;

            IF record_brand = '' AND record_supplier <> '' THEN
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
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION hede_refresh_document_product_links()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.document_type IS DISTINCT FROM '进货订单' THEN
                UPDATE inventory_details
                SET product_identity_id = NULL
                WHERE document_id = NEW.id
                  AND product_identity_id IS NOT NULL;
            ELSIF NEW.document_type IS DISTINCT FROM OLD.document_type
               OR NEW.supplier IS DISTINCT FROM OLD.supplier
               OR NEW.raw_payload IS DISTINCT FROM OLD.raw_payload THEN
                UPDATE inventory_details
                SET product_identity_id = NULL,
                    product_code = product_code
                WHERE document_id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$
    """))


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
    connection.execute(text(f"DROP TRIGGER IF EXISTS trg_hede_product_identity_sync ON {table_name}"))
    connection.execute(text(f"""
        CREATE TRIGGER trg_hede_product_identity_sync
        AFTER INSERT OR DELETE OR UPDATE OF sku, original_sku, deleted_at ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION hede_sync_product_archive_identity('{brand_literal}')
    """))


def _backfill_purchase_order_details(connection: Connection) -> None:
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
                        WHERE lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                    )
                ) AS brand
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE record.document_type = '进货订单'
              AND detail.product_identity_id IS NULL
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
                        WHERE lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                    )
                ) AS brand
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE record.document_type = '进货订单'
              AND detail.product_identity_id IS NULL
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
                        WHERE lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
                    )
                ) AS brand
            FROM inventory_details AS detail
            JOIN inventory_records AS record ON record.id = detail.document_id
            WHERE record.document_type = '进货订单'
              AND detail.product_identity_id IS NULL
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
            WHERE record.document_type = '进货订单'
              AND detail.product_identity_id IS NULL
              AND NULLIF(btrim(detail.product_code), '') IS NOT NULL
              AND NULLIF(lower(btrim(COALESCE(record.raw_payload ->> 'brand', ''))), '') IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM suppliers AS supplier
                  WHERE lower(btrim(supplier.name)) = lower(btrim(COALESCE(record.supplier, '')))
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
        # soon as both purchase-order tables exist.
        return

    connection.execute(text(
        "ALTER TABLE IF EXISTS inventory_details "
        "ADD COLUMN IF NOT EXISTS product_identity_id BIGINT"
    ))
    connection.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_inventory_details_product_identity'
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

    connection.execute(text(
        "DROP TRIGGER IF EXISTS trg_hede_purchase_detail_product_link ON inventory_details"
    ))
    connection.execute(text("""
        CREATE TRIGGER trg_hede_purchase_detail_product_link
        BEFORE INSERT OR UPDATE OF product_code, product_identity_id, document_id
        ON inventory_details
        FOR EACH ROW
        EXECUTE FUNCTION hede_link_purchase_order_detail_product()
    """))
    connection.execute(text(
        "DROP TRIGGER IF EXISTS trg_hede_inventory_record_product_links ON inventory_records"
    ))
    connection.execute(text("""
        CREATE TRIGGER trg_hede_inventory_record_product_links
        AFTER UPDATE OF document_type, supplier, raw_payload
        ON inventory_records
        FOR EACH ROW
        EXECUTE FUNCTION hede_refresh_document_product_links()
    """))
    connection.execute(text("""
        UPDATE inventory_details AS detail
        SET product_identity_id = NULL
        FROM inventory_records AS record
        WHERE detail.document_id = record.id
          AND record.document_type <> '进货订单'
          AND detail.product_identity_id IS NOT NULL
    """))
    _backfill_purchase_order_details(connection)


def product_archive_identity_coverage(connection: Connection) -> Mapping[str, int]:
    row = connection.execute(text("""
        SELECT
            count(*) FILTER (WHERE record.document_type = '进货订单') AS purchase_details,
            count(*) FILTER (
                WHERE record.document_type = '进货订单'
                  AND detail.product_identity_id IS NOT NULL
            ) AS linked_purchase_details,
            count(*) FILTER (
                WHERE record.document_type <> '进货订单'
                  AND detail.product_identity_id IS NOT NULL
            ) AS incorrectly_linked_non_purchase_details
        FROM inventory_details AS detail
        JOIN inventory_records AS record ON record.id = detail.document_id
    """)).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}
