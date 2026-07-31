"""Remove redundant product-goods snapshot indexes and add prefix-query indexes."""

from __future__ import annotations

import re

from sqlalchemy import create_engine, inspect, text

from config import load_settings


_YEAR_TABLE_PATTERN = re.compile(r"^(?:jst_daily_sales|vip_daily_sales|product_goods_historical_sales|product_goods_detail_snapshots)_\d{4}$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def _identifier(value: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Unsupported identifier: {value}")
    return value


def _index_exists(connection, index_name: str) -> bool:
    return connection.execute(
        text("SELECT to_regclass(:index_name) IS NOT NULL"),
        {"index_name": f"public.{index_name}"},
    ).scalar_one()


def _ensure_index(connection, *, index_name: str, table_name: str, definition: str) -> None:
    index_name = _identifier(index_name)
    table_name = _identifier(table_name)
    if _index_exists(connection, index_name):
        print(f"kept {index_name}", flush=True)
        return
    connection.execute(
        text(
            f"CREATE INDEX CONCURRENTLY {index_name} "
            f"ON public.{table_name} {definition}"
        )
    )
    print(f"created {index_name}", flush=True)


def _ensure_pattern_index(connection, *, index_name: str, table_name: str, definition: str) -> None:
    index_name = _identifier(index_name)
    table_name = _identifier(table_name)
    current_definition = connection.execute(
        text("SELECT pg_get_indexdef(to_regclass(:index_name))"),
        {"index_name": f"public.{index_name}"},
    ).scalar_one_or_none()
    if current_definition and "text_pattern_ops" in current_definition:
        print(f"kept {index_name}", flush=True)
        return

    upgrade_index_name = f"{index_name}_upgrade"
    _ensure_index(
        connection,
        index_name=upgrade_index_name,
        table_name=table_name,
        definition=definition,
    )
    if _index_exists(connection, index_name):
        connection.execute(text(f"DROP INDEX CONCURRENTLY public.{index_name}"))
        print(f"dropped {index_name}", flush=True)
    connection.execute(
        text(f"ALTER INDEX public.{_identifier(upgrade_index_name)} RENAME TO {index_name}")
    )
    print(f"upgraded {index_name}", flush=True)


def main() -> None:
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, future=True)
    table_names = sorted(inspect(engine).get_table_names())

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        for table_name in table_names:
            if not _YEAR_TABLE_PATTERN.fullmatch(table_name):
                continue
            if table_name.startswith("product_goods_detail_snapshots_"):
                redundant_index = f"idx_{table_name}_brand_date_goods"
                if _index_exists(connection, redundant_index):
                    connection.execute(text(f"DROP INDEX CONCURRENTLY public.{_identifier(redundant_index)}"))
                    print(f"dropped redundant {redundant_index}", flush=True)
            elif table_name.startswith("jst_daily_sales_"):
                _ensure_index(
                    connection,
                    index_name=f"idx_{table_name}_product_code_pattern",
                    table_name=table_name,
                    definition="(product_code text_pattern_ops)",
                )
                _ensure_index(
                    connection,
                    index_name=f"idx_{table_name}_style_code",
                    table_name=table_name,
                    definition="(style_code)",
                )
            elif table_name.startswith("vip_daily_sales_"):
                _ensure_index(
                    connection,
                    index_name=f"idx_{table_name}_goods_code_pattern",
                    table_name=table_name,
                    definition="(goods_code text_pattern_ops)",
                )
                _ensure_index(
                    connection,
                    index_name=f"idx_{table_name}_style_code",
                    table_name=table_name,
                    definition="(style_code)",
                )
            elif table_name.startswith("product_goods_historical_sales_"):
                _ensure_pattern_index(
                    connection,
                    index_name=f"idx_{table_name}_product",
                    table_name=table_name,
                    definition="(product_code text_pattern_ops)",
                )
                _ensure_pattern_index(
                    connection,
                    index_name=f"idx_{table_name}_original",
                    table_name=table_name,
                    definition="(original_sku text_pattern_ops)",
                )
                _ensure_pattern_index(
                    connection,
                    index_name=f"idx_{table_name}_brand_product",
                    table_name=table_name,
                    definition="(brand, product_code text_pattern_ops)",
                )

        _ensure_pattern_index(
            connection,
            index_name="idx_jst_full_stock_product_code",
            table_name="jst_full_stock",
            definition="(product_code text_pattern_ops)",
        )


if __name__ == "__main__":
    main()
