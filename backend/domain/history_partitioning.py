from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection


_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class HistoryPartitionSpec:
    table_name: str
    partition_expression: str
    source_date_expression: str
    indexes: tuple[tuple[str, str], ...]
    unique_indexes: tuple[tuple[str, str], ...] = ()
    normalized_view_sql: str | None = None


AFTERSALE_PARTITION_SPEC = HistoryPartitionSpec(
    table_name="jst_aftersale_returns",
    partition_expression=(
        "(COALESCE(application_date_value, order_date_value, order_time_value))"
    ),
    source_date_expression=(
        "COALESCE(application_date_value, order_date_value, order_time_value)"
    ),
    indexes=(
        ("idx_jst_aftersale_returns_id", "id"),
        (
            "idx_jst_aftersale_returns_business_date",
            "(COALESCE(application_date_value, order_date_value, order_time_value))",
        ),
        ("idx_jst_aftersale_returns_original_code", "original_goods_code"),
        ("idx_jst_aftersale_returns_order_date", "order_date_value"),
        ("idx_jst_aftersale_returns_order_time", "order_time_value"),
        ("idx_jst_aftersale_returns_application_date", "application_date_value"),
        (
            "idx_jst_aftersale_returns_business_code",
            "(COALESCE(application_date_value, order_date_value, order_time_value)), "
            "original_goods_code",
        ),
    ),
    normalized_view_sql=(
        "CREATE VIEW public.v_jst_aftersale_returns_normalized AS "
        "SELECT source.*, COALESCE(source.application_date_value, "
        "source.order_date_value, source.order_time_value) AS business_date "
        "FROM public.jst_aftersale_returns AS source"
    ),
)


MONTHLY_ORDER_PARTITION_SPEC = HistoryPartitionSpec(
    table_name="jst_monthly_orders",
    partition_expression="order_time_at",
    source_date_expression="order_time_at",
    indexes=(
        ("idx_jst_monthly_orders_order_time_at", "order_time_at"),
        ("idx_jst_monthly_orders_product_code", "product_code"),
        ("idx_jst_monthly_orders_style_code", "style_code"),
        ("idx_jst_monthly_orders_ship_date_value", "ship_date_value"),
        (
            "idx_jst_monthly_orders_time_product",
            "order_time_at, product_code",
        ),
        ("idx_jst_monthly_orders_style_time", "style_code, order_time_at"),
    ),
    unique_indexes=(
        (
            "uq_jst_monthly_orders_order_time_record_key",
            "order_time_at, record_key",
        ),
    ),
    normalized_view_sql=(
        "CREATE VIEW public.v_jst_monthly_orders_normalized AS "
        "SELECT orders.*, orders.order_time_at AS order_time_value "
        "FROM public.jst_monthly_orders AS orders"
    ),
)


DEWU_PARTITION_SPEC = HistoryPartitionSpec(
    table_name="dewu_orders",
    partition_expression="order_date",
    source_date_expression="order_date",
    indexes=(
        ("idx_dewu_orders_id", "id"),
        ("idx_dewu_orders_brand_order_date", "brand_group, order_date"),
        ("idx_dewu_orders_order_number", "order_number"),
        ("idx_dewu_orders_goods_code", "goods_code text_pattern_ops"),
        ("idx_dewu_orders_sku_id", "sku_id"),
        ("idx_dewu_orders_order_status", "order_status"),
    ),
)


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsupported PostgreSQL identifier: {value!r}")
    return value


def _is_postgresql(connection: Connection) -> bool:
    dialect = getattr(connection, "dialect", None)
    return getattr(dialect, "name", None) == "postgresql"


def is_partitioned_table(connection: Connection, table_name: str) -> bool:
    if not _is_postgresql(connection):
        return False
    table_name = _identifier(table_name)
    return bool(
        connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_class
                    WHERE oid = to_regclass(:qualified_name)
                      AND relkind = 'p'
                )
                """
            ),
            {"qualified_name": f"public.{table_name}"},
        ).scalar_one()
    )


def ensure_annual_partitions(
    connection: Connection,
    table_name: str,
    years: Iterable[int] = (),
) -> list[str]:
    """Ensure annual partitions without changing non-partitioned installations."""
    if not _is_postgresql(connection):
        return []

    table_name = _identifier(table_name)
    if not is_partitioned_table(connection, table_name):
        return []

    current_year = date.today().year
    required_years = {
        year
        for year in (*years, current_year, current_year + 1)
        if 2000 <= int(year) <= 2200
    }
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
        {"lock_name": f"annual-partitions:{table_name}"},
    )

    created: list[str] = []
    for year in sorted(required_years):
        child_name = _identifier(f"{table_name}_{year}")
        attached = bool(
            connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_inherits
                        WHERE inhparent = to_regclass(:parent_name)
                          AND inhrelid = to_regclass(:child_name)
                    )
                    """
                ),
                {
                    "parent_name": f"public.{table_name}",
                    "child_name": f"public.{child_name}",
                },
            ).scalar_one()
        )
        if attached:
            continue

        existing_relation = connection.execute(
            text("SELECT to_regclass(:child_name)"),
            {"child_name": f"public.{child_name}"},
        ).scalar_one()
        if existing_relation is not None:
            raise RuntimeError(
                f"{child_name} exists but is not attached to {table_name}"
            )

        connection.execute(
            text(
                f"CREATE TABLE public.{child_name} "
                f"PARTITION OF public.{table_name} "
                f"FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')"
            )
        )
        connection.execute(
            text(
                f"COMMENT ON TABLE public.{child_name} IS "
                f"'Annual history archive for {table_name}, year {year}'"
            )
        )
        created.append(child_name)

    default_name = _identifier(f"{table_name}_default")
    default_attached = bool(
        connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_inherits
                    WHERE inhparent = to_regclass(:parent_name)
                      AND inhrelid = to_regclass(:child_name)
                )
                """
            ),
            {
                "parent_name": f"public.{table_name}",
                "child_name": f"public.{default_name}",
            },
        ).scalar_one()
    )
    if not default_attached:
        existing_default = connection.execute(
            text("SELECT to_regclass(:child_name)"),
            {"child_name": f"public.{default_name}"},
        ).scalar_one()
        if existing_default is not None:
            raise RuntimeError(
                f"{default_name} exists but is not attached to {table_name}"
            )
        connection.execute(
            text(
                f"CREATE TABLE public.{default_name} "
                f"PARTITION OF public.{table_name} DEFAULT"
            )
        )
        connection.execute(
            text(
                f"COMMENT ON TABLE public.{default_name} IS "
                f"'Fallback archive partition for {table_name}'"
            )
        )
        created.append(default_name)

    return created


def _source_columns(connection: Connection, table_name: str) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT attname
                FROM pg_attribute
                WHERE attrelid = to_regclass(:qualified_name)
                  AND attnum > 0
                  AND NOT attisdropped
                ORDER BY attnum
                """
            ),
            {"qualified_name": f"public.{table_name}"},
        )
    ]


def _year_counts(
    connection: Connection,
    table_name: str,
    date_expression: str,
) -> dict[int | None, int]:
    rows = connection.execute(
        text(
            f"SELECT EXTRACT(YEAR FROM {date_expression})::INTEGER AS data_year, "
            f"COUNT(*) AS row_count FROM public.{table_name} "
            "GROUP BY 1 ORDER BY 1 NULLS LAST"
        )
    ).all()
    return {
        int(year) if year is not None else None: int(row_count)
        for year, row_count in rows
    }


def migrate_history_table(
    connection: Connection,
    spec: HistoryPartitionSpec,
) -> dict[str, object]:
    """Atomically replace a regular history table with an annual partition parent."""
    if not _is_postgresql(connection):
        raise RuntimeError("History partition migration requires PostgreSQL")

    table_name = _identifier(spec.table_name)
    relation_kind = connection.execute(
        text(
            "SELECT relkind FROM pg_class "
            "WHERE oid = to_regclass(:qualified_name)"
        ),
        {"qualified_name": f"public.{table_name}"},
    ).scalar_one_or_none()
    if relation_kind is None:
        return {"table": table_name, "status": "missing"}
    if relation_kind == "p":
        source_years = _year_counts(
            connection,
            table_name,
            spec.source_date_expression,
        )
        created = ensure_annual_partitions(
            connection,
            table_name,
            (year for year in source_years if year is not None),
        )
        connection.execute(
            text(
                f"COMMENT ON TABLE public.{table_name} IS "
                f"'Annual partitioned history; no automatic deletion'"
            )
        )
        return {
            "table": table_name,
            "status": "already_partitioned",
            "rows_by_year": source_years,
            "created_partitions": created,
        }
    if relation_kind != "r":
        raise RuntimeError(f"Unsupported relation kind for {table_name}: {relation_kind}")

    staging_name = _identifier(f"{table_name}_partitioned_0064")
    backup_name = _identifier(f"{table_name}_unpartitioned_0064")
    for temporary_name in (staging_name, backup_name):
        if connection.execute(
            text("SELECT to_regclass(:qualified_name)"),
            {"qualified_name": f"public.{temporary_name}"},
        ).scalar_one() is not None:
            raise RuntimeError(
                f"Temporary migration relation already exists: {temporary_name}"
            )

    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
        {"lock_name": f"history-partition-migration:{table_name}"},
    )
    connection.execute(text(f"LOCK TABLE public.{table_name} IN ACCESS EXCLUSIVE MODE"))
    if table_name == "jst_monthly_orders":
        connection.execute(
            text(
                "ALTER TABLE public.jst_monthly_orders "
                "ADD COLUMN IF NOT EXISTS record_key TEXT"
            )
        )

    source_columns = _source_columns(connection, table_name)
    source_count = int(
        connection.execute(text(f"SELECT COUNT(*) FROM public.{table_name}")).scalar_one()
    )
    source_years = _year_counts(
        connection,
        table_name,
        spec.source_date_expression,
    )

    connection.execute(
        text(
            f"CREATE TABLE public.{staging_name} ("
            f"LIKE public.{table_name} INCLUDING DEFAULTS INCLUDING GENERATED "
            f"INCLUDING CONSTRAINTS EXCLUDING IDENTITY EXCLUDING INDEXES"
            f") PARTITION BY RANGE ({spec.partition_expression})"
        )
    )

    sequence_name = _identifier(f"{table_name}_partition_id_seq")
    connection.execute(text(f"CREATE SEQUENCE public.{sequence_name}"))
    connection.execute(
        text(
            f"ALTER TABLE public.{staging_name} ALTER COLUMN id "
            f"SET DEFAULT nextval('public.{sequence_name}'::regclass)"
        )
    )
    connection.execute(
        text(
            f"ALTER SEQUENCE public.{sequence_name} "
            f"OWNED BY public.{staging_name}.id"
        )
    )

    years = [year for year in source_years if year is not None]
    current_year = date.today().year
    if years:
        years = list(range(min(years), max(max(years), current_year + 1) + 1))
    else:
        years = [current_year, current_year + 1]
    for year in years:
        child_name = _identifier(f"{table_name}_{year}")
        connection.execute(
            text(
                f"CREATE TABLE public.{child_name} "
                f"PARTITION OF public.{staging_name} "
                f"FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')"
            )
        )
        connection.execute(
            text(
                f"COMMENT ON TABLE public.{child_name} IS "
                f"'Annual history archive for {table_name}, year {year}'"
            )
        )
    default_name = _identifier(f"{table_name}_default")
    connection.execute(
        text(
            f"CREATE TABLE public.{default_name} "
            f"PARTITION OF public.{staging_name} DEFAULT"
        )
    )

    quoted_source_columns = ", ".join(f'"{column}"' for column in source_columns)
    connection.execute(
        text(
            f"INSERT INTO public.{staging_name} ({quoted_source_columns}) "
            f"SELECT {quoted_source_columns} FROM public.{table_name}"
        )
    )

    migrated_count = int(
        connection.execute(text(f"SELECT COUNT(*) FROM public.{staging_name}")).scalar_one()
    )
    migrated_years = _year_counts(
        connection,
        staging_name,
        spec.source_date_expression,
    )
    if migrated_count != source_count or migrated_years != source_years:
        raise RuntimeError(
            f"Migration validation failed for {table_name}: "
            f"rows {source_count} -> {migrated_count}, "
            f"years {source_years} -> {migrated_years}"
        )

    normalized_view_name = {
        "jst_monthly_orders": "v_jst_monthly_orders_normalized",
        "jst_aftersale_returns": "v_jst_aftersale_returns_normalized",
    }.get(table_name)
    if normalized_view_name:
        connection.execute(
            text(f"DROP VIEW IF EXISTS public.{normalized_view_name}")
        )
    connection.execute(
        text(f"ALTER TABLE public.{table_name} RENAME TO {backup_name}")
    )
    connection.execute(
        text(f"ALTER TABLE public.{staging_name} RENAME TO {table_name}")
    )
    connection.execute(text(f"DROP TABLE public.{backup_name}"))

    for index_name, index_columns in spec.indexes:
        _identifier(index_name)
        connection.execute(
            text(
                f"CREATE INDEX {index_name} ON public.{table_name} "
                f"({index_columns})"
            )
        )
    for index_name, index_columns in spec.unique_indexes:
        _identifier(index_name)
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX {index_name} ON public.{table_name} "
                f"({index_columns})"
            )
        )
    if spec.normalized_view_sql:
        connection.execute(text(spec.normalized_view_sql))
    connection.execute(
        text(
            f"SELECT setval('public.{sequence_name}', "
            f"COALESCE((SELECT MAX(id) FROM public.{table_name}), 1), "
            f"EXISTS (SELECT 1 FROM public.{table_name}))"
        )
    )
    connection.execute(
        text(
            f"COMMENT ON TABLE public.{table_name} IS "
            f"'Annual partitioned history; no automatic deletion'"
        )
    )
    return {
        "table": table_name,
        "status": "migrated",
        "row_count": migrated_count,
        "rows_by_year": migrated_years,
        "partitions": [f"{table_name}_{year}" for year in years]
        + [default_name],
    }


def migrate_order_history_tables(connection: Connection) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    results.append(migrate_history_table(connection, MONTHLY_ORDER_PARTITION_SPEC))
    results.append(migrate_history_table(connection, AFTERSALE_PARTITION_SPEC))
    results.append(migrate_history_table(connection, DEWU_PARTITION_SPEC))
    return results
