"""Attach legacy annual tables to unified PostgreSQL partition parents."""
from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import create_engine, text

from config import load_settings
from domain.fine_table_snapshot_schema import refresh_fine_table_snapshot_compatibility_view
from domain.legacy_partitioning import LegacyPartitionTarget, migrate_legacy_partitions


YEARLY_TARGETS = (
    ("jst_daily_sales", "jst_daily_sales", "sales_date", (2026,)),
    ("vip_daily_sales", "vip_daily_sales", "sales_date", (2026,)),
    ("product_goods_detail_snapshots", "product_goods_detail_snapshots", "snapshot_date", (2024, 2025, 2026)),
    ("product_goods_historical_sales", "product_goods_historical_sales", "sales_date", (2024, 2025)),
    ("product_goods_historical_orders", "product_goods_historical_orders", "order_date", (2022, 2023, 2024, 2025, 2026)),
)
FINE_PARENT_NAME = "fine_table_snapshot_rows"
FINE_CHILDREN = ("fine_table_snapshot_rows_2024", "fine_table_snapshot_rows_2025", "fine_table_snapshot_rows_2026")
FINE_BACKFILL_BATCH_SIZE = 256


def _year_bounds(year: int) -> tuple[str, str]:
    return f"{year:04d}-01-01", f"{year + 1:04d}-01-01"


def _build_yearly_targets() -> list[LegacyPartitionTarget]:
    targets: list[LegacyPartitionTarget] = []
    for parent_name, prefix, partition_key, years in YEARLY_TARGETS:
        for year in years:
            lower_bound, upper_bound = _year_bounds(year)
            targets.append(
                LegacyPartitionTarget(
                    parent_name=parent_name,
                    child_name=f"{prefix}_{year:04d}",
                    partition_key=partition_key,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
            )
    return targets


def _build_fine_targets(engine, *, require_prepared: bool = True) -> list[LegacyPartitionTarget]:
    with engine.connect() as connection:
        existing_tables = [
            table_name for table_name in FINE_CHILDREN if _fine_table_exists(connection, table_name)
        ]
        missing_columns = [
            table_name
            for table_name in existing_tables
            if not connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                          AND column_name = 'snapshot_date'
                    )
                    """
                ),
                {"table_name": table_name},
            ).scalar_one()
        ]
    if missing_columns:
        if require_prepared:
            raise ValueError(
                "Fine table snapshot dates have not been prepared: " + ", ".join(missing_columns)
            )
        return [
            LegacyPartitionTarget(
                parent_name=FINE_PARENT_NAME,
                child_name=table_name,
                partition_key="snapshot_date",
                lower_bound=_year_bounds(int(table_name[-4:]))[0],
                upper_bound=_year_bounds(int(table_name[-4:]))[1],
            )
            for table_name in existing_tables
        ]
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name, min_snapshot_date, max_snapshot_date, missing_snapshot_dates
                FROM (
                    SELECT
                        'fine_table_snapshot_rows_2024' AS table_name,
                        min(snapshot_date) AS min_snapshot_date,
                        max(snapshot_date) AS max_snapshot_date,
                        count(*) FILTER (WHERE snapshot_date IS NULL) AS missing_snapshot_dates
                    FROM fine_table_snapshot_rows_2024
                    UNION ALL
                    SELECT
                        'fine_table_snapshot_rows_2025',
                        min(snapshot_date),
                        max(snapshot_date),
                        count(*) FILTER (WHERE snapshot_date IS NULL)
                    FROM fine_table_snapshot_rows_2025
                    UNION ALL
                    SELECT
                        'fine_table_snapshot_rows_2026',
                        min(snapshot_date),
                        max(snapshot_date),
                        count(*) FILTER (WHERE snapshot_date IS NULL)
                    FROM fine_table_snapshot_rows_2026
                ) AS batches
                ORDER BY table_name
                """
            )
        ).mappings().all()
    targets: list[LegacyPartitionTarget] = []
    for row in rows:
        if int(row["missing_snapshot_dates"] or 0):
            raise ValueError(f"Fine table snapshot dates have not been backfilled: {row['table_name']}")
        min_snapshot_date = row["min_snapshot_date"]
        max_snapshot_date = row["max_snapshot_date"]
        if min_snapshot_date is None or max_snapshot_date is None:
            raise ValueError(f"Fine table snapshot table has no valid snapshot dates: {row['table_name']}")
        year = int(str(row["table_name"])[-4:])
        if min_snapshot_date.year != year or max_snapshot_date.year != year:
            raise ValueError(f"Fine table snapshot dates do not match partition year: {row['table_name']}")
        lower_bound, upper_bound = _year_bounds(year)
        targets.append(
            LegacyPartitionTarget(
                parent_name=FINE_PARENT_NAME,
                child_name=str(row["table_name"]),
                partition_key="snapshot_date",
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
        )
    return targets


def _fine_table_exists(connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": f"public.{table_name}"},
        ).scalar_one()
    )


def _ensure_fine_snapshot_date_column(engine, table_name: str) -> None:
    with engine.connect() as connection:
        has_snapshot_date = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = 'snapshot_date'
                )
                """
            ),
            {"table_name": table_name},
        ).scalar_one()
    if not has_snapshot_date:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f"ALTER TABLE public.{table_name} ADD COLUMN snapshot_date DATE"))

    with engine.begin() as connection:
        batch_rows = connection.execute(
            text(
                f"""
                SELECT DISTINCT batches.id, batches.snapshot_date
                FROM public.{table_name} AS rows
                JOIN public.fine_table_snapshot_batches AS batches ON batches.id = rows.batch_id
                WHERE rows.snapshot_date IS NULL
                ORDER BY batches.id
                """
            )
        ).mappings().all()

    for start in range(0, len(batch_rows), FINE_BACKFILL_BATCH_SIZE):
        chunk = batch_rows[start:start + FINE_BACKFILL_BATCH_SIZE]
        batch_ids = [int(row["id"]) for row in chunk]
        snapshot_dates = [row["snapshot_date"] for row in chunk]
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    UPDATE public.{table_name} AS rows
                    SET snapshot_date = source.snapshot_date
                    FROM unnest(CAST(:batch_ids AS bigint[]), CAST(:snapshot_dates AS date[]))
                        AS source(id, snapshot_date)
                    WHERE rows.batch_id = source.id
                      AND rows.snapshot_date IS NULL
                    """
                ),
                {"batch_ids": batch_ids, "snapshot_dates": snapshot_dates},
            )
        print(
            f"[BACKFILL] {table_name} batches {start + 1}-{start + len(chunk)} of {len(batch_rows)}",
            flush=True,
        )

    with engine.connect() as connection:
        missing_count = connection.execute(
            text(f"SELECT count(*) FROM public.{table_name} WHERE snapshot_date IS NULL")
        ).scalar_one()
        mismatch_count = connection.execute(
            text(
                f"""
                SELECT count(*)
                FROM public.{table_name} AS rows
                JOIN public.fine_table_snapshot_batches AS batches ON batches.id = rows.batch_id
                WHERE rows.snapshot_date IS DISTINCT FROM batches.snapshot_date
                """
            )
        ).scalar_one()
    if missing_count or mismatch_count:
        raise ValueError(
            f"Fine table snapshot date verification failed for {table_name}: "
            f"missing={missing_count}, mismatched={mismatch_count}"
        )


def _prepare_fine_snapshot_dates(engine) -> None:
    with engine.connect() as connection:
        existing_tables = [table_name for table_name in FINE_CHILDREN if _fine_table_exists(connection, table_name)]
    for table_name in existing_tables:
        print(f"[PREPARE] backfilling {table_name}.snapshot_date", flush=True)
        _ensure_fine_snapshot_date_column(engine, table_name)


def _target_summary(targets: list[LegacyPartitionTarget]) -> list[str]:
    return [
        f"{target.child_name} -> {target.parent_name} ({target.partition_key}: {target.lower_bound}..{target.upper_bound})"
        for target in targets
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移历史分年表为统一分区父表")
    parser.add_argument("--apply", action="store_true", help="执行迁移；未传入时仅输出计划")
    parser.add_argument("--include-fine", action="store_true", help="包含精细表历史快照的物理分区迁移")
    parser.add_argument("--prepare-only", action="store_true", help="仅回填精细表快照日期，不挂载分区")
    args = parser.parse_args()

    settings = load_settings()
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    targets = _build_yearly_targets()
    if args.include_fine:
        if args.apply or args.prepare_only:
            _prepare_fine_snapshot_dates(engine)
        if args.prepare_only:
            print("[DONE] fine-table snapshot dates prepared")
            return 0
        targets.extend(_build_fine_targets(engine, require_prepared=args.apply))

    for line in _target_summary(targets):
        print(f"[PLAN] {line}")
    if not args.apply:
        return 0

    migrated = migrate_legacy_partitions(engine, targets)
    refresh_fine_table_snapshot_compatibility_view(engine)
    print(f"[DONE] migrated {len(migrated)} partitions on {date.today().isoformat()}")
    for child_name in migrated:
        print(f"[ATTACHED] {child_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
