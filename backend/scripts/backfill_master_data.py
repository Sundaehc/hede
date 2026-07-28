"""Populate the non-blocking master-data layer from existing business tables."""
from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import create_engine, inspect, text

from config import load_settings
from domain import master_data_schema  # noqa: F401 - register master-data tables
from domain.master_data_schema import MASTER_DATA_ALIASES_TABLE, MASTER_DATA_ENTITIES_TABLE, PRODUCT_CODE_MAPPINGS_TABLE
from domain.schema import METADATA, PRODUCT_TABLES


@dataclass(frozen=True)
class EntitySource:
    entity_type: str
    table_name: str
    column_name: str
    source_system: str


ENTITY_SOURCES = (
    EntitySource("supplier", "suppliers", "name", "supplier_management"),
    EntitySource("supplier", "inventory_records", "supplier", "inventory"),
    EntitySource("supplier", "gj_merged_product_info", "primary_supplier", "jst_product_profile"),
    EntitySource("supplier", "jst_daily_sales_2026", "supplier", "jst_daily_sales"),
    EntitySource("warehouse", "inventory_records", "warehouse", "inventory"),
    EntitySource("warehouse", "warehouses", "name", "warehouse_management"),
    EntitySource("shop", "general_customer_shops", "shop_name", "general_customer"),
    EntitySource("shop", "jst_monthly_orders", "shop_name", "jst_monthly_orders"),
    EntitySource("channel", "jst_daily_sales", "channel", "jst_daily_sales"),
    EntitySource("channel", "product_goods_historical_sales", "channel", "historical_sales"),
    EntitySource("channel", "product_goods_shop_channel_mappings", "channel", "shop_channel_mapping"),
)


def _quote(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise ValueError(f"Invalid identifier: {identifier}")
    return f'"{identifier}"'


def _existing_columns(engine, table_name: str) -> set[str]:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def ensure_master_data_relationship_constraints(engine) -> None:
    """Upgrade legacy one-to-one code mappings to a lossless relationship key."""

    constraint_name = "uq_product_code_mappings_brand_type_value_canonical"
    index_name = "idx_product_code_mappings_relationship_unique"
    with engine.connect() as connection:
        constraints = {
            row["conname"]
            for row in connection.execute(
                text(
                    """
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'public.product_code_mappings'::regclass
                    """
                )
            ).mappings()
        }
    if constraint_name in constraints:
        return

    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(
            text(
                """
                ALTER TABLE public.product_code_mappings
                DROP CONSTRAINT IF EXISTS uq_product_code_mappings_brand_type_value
                """
            )
        )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(
            text(
                f"""
                CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                ON public.product_code_mappings
                    (brand, code_type, code_value, canonical_product_code)
                """
            )
        )
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(
            text(
                f"""
                ALTER TABLE public.product_code_mappings
                ADD CONSTRAINT {constraint_name}
                UNIQUE USING INDEX {index_name}
                """
            )
        )


def _upsert_entity_source(engine, source: EntitySource) -> int:
    columns = _existing_columns(engine, source.table_name)
    if source.column_name not in columns:
        return 0

    table = _quote(source.table_name)
    column = _quote(source.column_name)
    with engine.begin() as connection:
        result = connection.execute(
            text(
                f"""
                WITH source_values AS (
                    SELECT DISTINCT btrim({column}::text) AS value
                    FROM public.{table}
                    WHERE nullif(btrim({column}::text), '') IS NOT NULL
                ), entities AS (
                    INSERT INTO public.master_data_entities
                        (entity_type, canonical_name, raw_payload)
                    SELECT :entity_type, value,
                           jsonb_build_object(
                               'source_table', CAST(:table_name AS text),
                               'source_column', CAST(:column_name AS text)
                           )
                    FROM source_values
                    ON CONFLICT (entity_type, canonical_name) DO NOTHING
                    RETURNING id, canonical_name
                ), resolved_entities AS (
                    SELECT id, canonical_name FROM entities
                    UNION ALL
                    SELECT id, canonical_name
                    FROM public.master_data_entities
                    WHERE entity_type = :entity_type
                      AND canonical_name IN (SELECT value FROM source_values)
                )
                INSERT INTO public.master_data_aliases
                    (entity_id, entity_type, alias_name, normalized_name, source_system, raw_payload)
                SELECT id, :entity_type, canonical_name,
                       lower(regexp_replace(canonical_name, '\\s+', '', 'g')),
                       :source_system,
                       jsonb_build_object(
                           'source_table', CAST(:table_name AS text),
                           'source_column', CAST(:column_name AS text)
                       )
                FROM resolved_entities
                ON CONFLICT (entity_type, normalized_name) DO NOTHING
                """
            ),
            {
                "entity_type": source.entity_type,
                "source_system": source.source_system,
                "table_name": source.table_name,
                "column_name": source.column_name,
            },
        )
        return result.rowcount if result.rowcount is not None else 0


def _upsert_product_archive_codes(engine) -> int:
    written = 0
    for brand, table in PRODUCT_TABLES.items():
        for code_type, column_name, canonical_column in (
            ("sku", "sku", "sku"),
            ("original_sku", "original_sku", "sku"),
        ):
            with engine.begin() as connection:
                result = connection.execute(
                    text(
                        f"""
                        INSERT INTO public.product_code_mappings
                            (brand, code_type, code_value, canonical_product_code, source_system, raw_payload)
                        SELECT :brand, :code_type, source.code_value, source.canonical_product_code,
                               'product_archive', jsonb_build_object('source_table', CAST(:table_name AS text))
                        FROM (
                            SELECT DISTINCT
                                btrim({_quote(column_name)}) AS code_value,
                                btrim({_quote(canonical_column)}) AS canonical_product_code
                            FROM public.{_quote(table.name)}
                            WHERE nullif(btrim({_quote(column_name)}), '') IS NOT NULL
                              AND nullif(btrim({_quote(canonical_column)}), '') IS NOT NULL
                        ) AS source
                        ON CONFLICT (brand, code_type, code_value, canonical_product_code)
                        DO UPDATE SET source_system = EXCLUDED.source_system,
                                      is_active = true,
                                      raw_payload = EXCLUDED.raw_payload,
                                      updated_at = date_trunc('minute', now())
                        WHERE product_code_mappings.source_system IS DISTINCT FROM EXCLUDED.source_system
                           OR product_code_mappings.is_active IS DISTINCT FROM true
                           OR product_code_mappings.raw_payload::text IS DISTINCT FROM EXCLUDED.raw_payload::text
                        """
                    ),
                    {"brand": brand, "code_type": code_type, "table_name": table.name},
                )
                written += result.rowcount if result.rowcount is not None else 0
    return written


def _upsert_sales_codes(engine) -> int:
    sources = (
        ("jst_daily_sales", "", "product_code", "product_code", "jst_daily_sales"),
        ("jst_daily_sales", "", "style_code", "product_code", "jst_daily_sales"),
        ("vip_daily_sales", "", "goods_code", "goods_code", "vip_daily_sales"),
        ("vip_daily_sales", "", "style_code", "goods_code", "vip_daily_sales"),
        ("product_goods_historical_sales", None, "product_code", "product_code", "historical_sales"),
        ("product_goods_historical_sales", None, "style_code", "product_code", "historical_sales"),
    )
    written = 0
    for table_name, fixed_brand, code_type, canonical_column, source_system in sources:
        columns = _existing_columns(engine, table_name)
        if code_type not in columns or canonical_column not in columns:
            continue
        brand_expression = ":fixed_brand"
        brand_filter = ""
        if fixed_brand is None and "brand" in columns:
            brand_expression = "coalesce(brand, '')"
        elif fixed_brand is None:
            continue
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    f"""
                    INSERT INTO public.product_code_mappings
                        (brand, code_type, code_value, canonical_product_code, source_system, raw_payload)
                    SELECT source.brand, :code_type, source.code_value,
                           source.canonical_product_code, :source_system,
                           jsonb_build_object('source_table', CAST(:table_name AS text))
                    FROM (
                        SELECT DISTINCT {brand_expression} AS brand,
                               btrim({_quote(code_type)}) AS code_value,
                               btrim({_quote(canonical_column)}) AS canonical_product_code
                        FROM public.{_quote(table_name)}
                        WHERE nullif(btrim({_quote(code_type)}), '') IS NOT NULL
                          AND nullif(btrim({_quote(canonical_column)}), '') IS NOT NULL
                    ) AS source
                    ON CONFLICT (brand, code_type, code_value, canonical_product_code)
                    DO UPDATE SET source_system = EXCLUDED.source_system,
                                  is_active = true,
                                  raw_payload = EXCLUDED.raw_payload,
                                  updated_at = date_trunc('minute', now())
                    WHERE product_code_mappings.source_system IS DISTINCT FROM EXCLUDED.source_system
                       OR product_code_mappings.is_active IS DISTINCT FROM true
                       OR product_code_mappings.raw_payload::text IS DISTINCT FROM EXCLUDED.raw_payload::text
                    """
                ),
                {
                    "fixed_brand": fixed_brand or "",
                    "code_type": code_type,
                    "source_system": source_system,
                    "table_name": table_name,
                },
            )
            written += result.rowcount if result.rowcount is not None else 0
    return written


def _refresh_views(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE OR REPLACE VIEW public.v_master_data_aliases AS
                SELECT aliases.entity_type, aliases.alias_name, aliases.normalized_name,
                       aliases.source_system, entities.id AS entity_id,
                       entities.canonical_name, entities.canonical_code, entities.is_active
                FROM public.master_data_aliases AS aliases
                JOIN public.master_data_entities AS entities ON entities.id = aliases.entity_id
                WHERE entities.is_active
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE OR REPLACE VIEW public.v_product_code_mappings AS
                SELECT brand, code_type, code_value, canonical_product_code, source_system
                FROM public.product_code_mappings
                WHERE is_active
                """
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="从业务表回填受控主数据与商品编码映射")
    parser.add_argument("--dry-run", action="store_true", help="仅创建表和视图，不回填数据")
    parser.add_argument("--include-facts", action="store_true", help="同步日销和历史销量中的编码映射")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    METADATA.create_all(engine, checkfirst=True)
    ensure_master_data_relationship_constraints(engine)
    if args.dry_run:
        _refresh_views(engine)
        print("[DRY_RUN] master-data tables and views are ready")
        return 0

    entity_count = sum(_upsert_entity_source(engine, source) for source in ENTITY_SOURCES)
    product_code_count = _upsert_product_archive_codes(engine)
    if args.include_facts:
        product_code_count += _upsert_sales_codes(engine)
    _refresh_views(engine)
    print(f"[DONE] master-data aliases inserted: {entity_count}; code mappings inserted: {product_code_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
