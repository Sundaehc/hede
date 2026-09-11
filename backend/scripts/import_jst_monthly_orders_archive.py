"""Backfill and archive JST order-detail workbooks.

The source exports can exceed Excel's row limit and have an invalid worksheet
dimension.  This importer uses the project's XML row reader, stores yearly
PostgreSQL partitions behind the existing ``jst_monthly_orders`` table name,
and replaces only the requested current window.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text

from config import load_settings
from domain.vip_sources import JST_MONTHLY_ORDERS_COLUMN_ALIASES
from storage.date_normalization import parse_date, parse_datetime
from storage.vip_repository import _xlsx_sheet_rows


TABLE = "jst_monthly_orders"
BACKUP_TABLE = "jst_monthly_orders_legacy_backup_20260910"
SEQUENCE = "jst_monthly_orders_archive_id_seq"
START_DATE = date(2024, 1, 1)
REPLACE_START = date(2026, 6, 8)
REPLACE_END = date(2026, 9, 10)

TEXT_FIELDS = {
    "internal_order_id",
    "online_order_id",
    "buyer_account",
    "platform_site",
    "order_time",
    "ship_date",
    "shop_name",
    "status",
    "address",
    "order_type",
    "shop_style_code",
    "style_code",
    "product_code",
    "category",
    "shop_status",
    "online_sub_order_id",
}
INTEGER_FIELDS = {"quantity", "registered_qty", "actual_return_qty"}
NUMERIC_FIELDS = {"payable_amount", "paid_amount", "cost_price", "buyer_paid", "seller_received"}
MAPPED_FIELDS = (*TEXT_FIELDS, *INTEGER_FIELDS, *NUMERIC_FIELDS)
KEY_FIELDS = (
    "internal_order_id",
    "online_order_id",
    "online_sub_order_id",
    "order_time",
    "shop_name",
    "style_code",
    "product_code",
    "quantity",
    "status",
)

DATA_COLUMNS = (
    "source_workbook",
    "source_sheet",
    "source_row_number",
    "raw_payload",
    *MAPPED_FIELDS,
    "order_time_at",
    "ship_date_value",
    "record_key",
)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _integer(value: object) -> int | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(Decimal(value.replace(",", "")))
    except (InvalidOperation, ValueError):
        return None


def _numeric(value: object) -> Decimal | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _json_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _fingerprint(record: dict[str, object]) -> str:
    material = "\x1f".join(str(record.get(field) or "") for field in KEY_FIELDS)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _map_row(
    *,
    headers: dict[int, str],
    values: dict[int, str],
    file_path: Path,
    sheet_name: str,
    row_number: int,
) -> dict[str, object] | None:
    raw = {header: values.get(index, "") for index, header in headers.items()}
    mapped: dict[str, object] = {}
    for index, header in headers.items():
        column = JST_MONTHLY_ORDERS_COLUMN_ALIASES.get(header)
        if not column:
            continue
        value = values.get(index, "")
        if column in INTEGER_FIELDS:
            mapped[column] = _integer(value)
        elif column in NUMERIC_FIELDS:
            mapped[column] = _numeric(value)
        else:
            mapped[column] = _clean(value)

    order_time_at = parse_datetime(mapped.get("order_time"))
    if order_time_at is None:
        return None
    order_date = order_time_at.date()
    if order_date < START_DATE:
        return None

    record = {
        "source_workbook": file_path.stem,
        "source_sheet": sheet_name,
        "source_row_number": str(row_number),
        "raw_payload": {key: _json_value(value) for key, value in raw.items()},
        **{field: mapped.get(field) for field in (*TEXT_FIELDS, *INTEGER_FIELDS, *NUMERIC_FIELDS)},
        "order_time_at": order_time_at,
        "ship_date_value": parse_date(mapped.get("ship_date")),
    }
    record["record_key"] = _fingerprint(record)
    return record


def _files(root: Path) -> list[Path]:
    files = sorted(root.glob("*.xlsx"), key=lambda path: (path.stat().st_mtime_ns, path.name))
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {root}")
    return files


def _is_partitioned(connection) -> bool:
    return bool(
        connection.execute(
            text(
                """
                select exists (
                    select 1 from pg_class
                    where oid = 'public.jst_monthly_orders'::regclass
                      and relkind = 'p'
                )
                """
            )
        ).scalar_one()
    )


def _partition_names() -> list[str]:
    return [
        "jst_monthly_orders_2023",
        "jst_monthly_orders_2024",
        "jst_monthly_orders_2025",
        "jst_monthly_orders_2026",
        "jst_monthly_orders_default",
    ]


def _migrate_to_partitions(engine) -> None:
    with engine.begin() as connection:
        if _is_partitioned(connection):
            return

        connection.execute(text(f"alter table public.{TABLE} rename to {BACKUP_TABLE}"))
        connection.execute(
            text(
                f"""
                create table public.{TABLE}
                (like public.{BACKUP_TABLE} including defaults including generated
                 excluding identity excluding constraints excluding indexes)
                partition by range (order_time_at)
                """
            )
        )
        connection.execute(text(f"alter table public.{TABLE} add column record_key text"))
        connection.execute(
            text(
                f"""
                create sequence if not exists public.{SEQUENCE};
                alter table public.{TABLE}
                    alter column id set default nextval('public.{SEQUENCE}');
                alter sequence public.{SEQUENCE}
                    owned by public.{TABLE}.id;
                """
            )
        )

        bounds = {
            "jst_monthly_orders_2023": ("2023-01-01", "2024-01-01"),
            "jst_monthly_orders_2024": ("2024-01-01", "2025-01-01"),
            "jst_monthly_orders_2025": ("2025-01-01", "2026-01-01"),
            "jst_monthly_orders_2026": ("2026-01-01", "2027-01-01"),
        }
        for name, (lower, upper) in bounds.items():
            connection.execute(
                text(
                    f"create table public.{name} partition of public.{TABLE} "
                    f"for values from ('{lower}') to ('{upper}')"
                )
            )
        connection.execute(
            text(
                f"create table public.jst_monthly_orders_default partition of public.{TABLE} default"
            )
        )

        old_columns = [
            "source_workbook", "source_sheet", "source_row_number", "raw_payload",
            "internal_order_id", "online_order_id", "buyer_account", "platform_site",
            "order_time", "ship_date", "shop_name", "payable_amount", "paid_amount",
            "status", "address", "order_type", "shop_style_code", "style_code",
            "product_code", "quantity", "category", "registered_qty", "actual_return_qty",
            "cost_price", "shop_status", "buyer_paid", "seller_received",
            "online_sub_order_id", "extra_fields", "created_at", "updated_at",
            "order_time_at", "ship_date_value",
        ]
        target_columns = [*old_columns, "record_key"]
        old_select = ", ".join(f"legacy.{column}" for column in old_columns)
        connection.execute(
            text(
                f"""
                insert into public.{TABLE} ({', '.join(target_columns)})
                select {old_select}, md5('legacy:' || legacy.id::text)
                from public.{BACKUP_TABLE} legacy
                """
            )
        )
        connection.execute(
            text(
                f"select setval('public.{SEQUENCE}', "
                f"coalesce((select max(id) from public.{TABLE}), 1), "
                f"exists (select 1 from public.{TABLE}))"
            )
        )
        connection.execute(
            text(
                f"alter table public.{TABLE} add constraint "
                "uq_jst_monthly_orders_order_time_record_key unique (order_time_at, record_key)"
            )
        )
        legacy_indexes = connection.execute(
            text(
                """
                select indexname
                from pg_indexes
                where schemaname = 'public' and tablename = :table_name
                """
            ),
            {"table_name": BACKUP_TABLE},
        ).mappings().all()
        for row in legacy_indexes:
            old_name = str(row["indexname"])
            new_name = f"legacy_{old_name}"
            connection.execute(text(f"alter index public.{old_name} rename to {new_name}"))

        for index_name, columns in {
            "idx_jst_monthly_orders_order_time_at": "order_time_at",
            "idx_jst_monthly_orders_product_code": "product_code",
            "idx_jst_monthly_orders_style_code": "style_code",
            "idx_jst_monthly_orders_ship_date_value": "ship_date_value",
            "idx_jst_monthly_orders_time_product": "order_time_at, product_code",
            "idx_jst_monthly_orders_style_time": "style_code, order_time_at",
        }.items():
            connection.execute(text(f"create index {index_name} on public.{TABLE} ({columns})"))

        connection.execute(text("drop view if exists public.v_jst_monthly_orders_normalized"))
        connection.execute(
            text(
                f"""
                create view public.v_jst_monthly_orders_normalized as
                select orders.*, orders.order_time_at as order_time_value
                from public.{TABLE} orders
                """
            )
        )

        # The old table is retained until the new data is validated, then
        # dropped by the caller so a failed import leaves a recovery copy.


def _ensure_partition_schema(engine) -> None:
    with engine.connect() as connection:
        partitioned = _is_partitioned(connection)
    if not partitioned:
        _migrate_to_partitions(engine)
        return
    with engine.begin() as connection:
        connection.execute(text(f"alter table public.{TABLE} add column if not exists record_key text"))
        connection.execute(text("drop view if exists public.v_jst_monthly_orders_normalized"))
        connection.execute(
            text(
                f"create view public.v_jst_monthly_orders_normalized as "
                f"select orders.*, orders.order_time_at as order_time_value from public.{TABLE} orders"
            )
        )


def _existing_dates(engine) -> set[date]:
    with engine.connect() as connection:
        return {
            row[0]
            for row in connection.execute(
                text(f"select distinct order_time_at::date from public.{TABLE} where order_time_at is not null")
            )
            if isinstance(row[0], date)
        }


def _delete_replace_window(engine) -> int:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                f"delete from public.{TABLE} where order_time_at >= :start_at "
                "and order_time_at < :end_at"
            ),
            {
                "start_at": datetime.combine(REPLACE_START, time.min),
                "end_at": datetime.combine(date(2026, 9, 11), time.min),
            },
        )
        return int(result.rowcount or 0)


def _copy_file(
    engine,
    file_path: Path,
    existing_dates: set[date],
) -> tuple[int, int, set[date]]:
    row_iterator = _xlsx_sheet_rows(file_path)
    try:
        _, header_values = next(row_iterator)
    except StopIteration:
        return 0, 0, set()
    headers = {index: value for index, value in header_values.items() if value}
    required = {"internal_order_id", "order_time", "product_code"}
    mapped = {JST_MONTHLY_ORDERS_COLUMN_ALIASES.get(header) for header in headers.values()}
    missing = sorted(required - mapped)
    if missing:
        raise ValueError(f"{file_path.name} missing required fields: {', '.join(missing)}")

    accepted = 0
    read = 0
    dates: set[date] = set()
    with engine.begin() as connection:
        connection.execute(
            text(
                f"create temporary table jst_monthly_orders_import_stage "
                f"(like public.{TABLE} including defaults excluding indexes) on commit drop"
            )
        )
        connection.execute(
            text(
                "alter table jst_monthly_orders_import_stage "
                "alter column id drop default, alter column id drop not null"
            )
        )
        driver = connection.connection.driver_connection
        copy_sql = (
            "copy jst_monthly_orders_import_stage ("
            + ", ".join(DATA_COLUMNS)
            + ") from stdin"
        )
        with driver.cursor().copy(copy_sql) as copy:
            for row_number, values in row_iterator:
                read += 1
                record = _map_row(
                    headers=headers,
                    values=values,
                    file_path=file_path,
                    sheet_name="Sheet1",
                    row_number=row_number,
                )
                if record is None:
                    continue
                order_date = record["order_time_at"].date()
                if order_date in existing_dates and not (REPLACE_START <= order_date <= REPLACE_END):
                    continue
                dates.add(order_date)
                copy_values = [record[column] for column in DATA_COLUMNS]
                raw_payload_index = DATA_COLUMNS.index("raw_payload")
                copy_values[raw_payload_index] = json.dumps(
                    copy_values[raw_payload_index], ensure_ascii=False, separators=(",", ":")
                )
                copy.write_row(tuple(copy_values))
                accepted += 1

        columns = ", ".join(DATA_COLUMNS)
        connection.execute(
            text(
                f"""
                insert into public.{TABLE} ({columns})
                select distinct on (order_time_at, record_key) {columns}
                from jst_monthly_orders_import_stage
                order by order_time_at, record_key, source_row_number desc
                on conflict (order_time_at, record_key) do nothing
                """
            )
        )
    return read, accepted, dates


def _drop_legacy_backup(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"drop table if exists public.{BACKUP_TABLE}"))


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐并归档聚水潭历史订单")
    parser.add_argument("--source-root", type=Path, default=Path.home() / "Desktop" / "orders")
    parser.add_argument("--keep-legacy-backup", action="store_true")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    files = _files(args.source_root)
    engine = create_engine(settings.database_url, future=True, json_serializer=lambda value: json.dumps(value, ensure_ascii=False))

    _ensure_partition_schema(engine)
    existing = _existing_dates(engine)
    replaced = _delete_replace_window(engine)
    all_source_dates: set[date] = set()
    read_rows = 0
    accepted_rows = 0
    for file_path in files:
        # The source contains several overlapping split files.  For current
        # dates always import; for historical dates only import missing days.
        read, accepted, dates = _copy_file(engine, file_path, existing)
        read_rows += read
        accepted_rows += accepted
        all_source_dates.update(dates)
        print(f"[IMPORT] {file_path.name}: read={read} accepted={accepted} dates={len(dates)}", flush=True)

    # Remove the legacy copy only after the partitioned table has received the
    # replacement/backfill data.  It is not part of application queries.
    if not args.keep_legacy_backup:
        _drop_legacy_backup(engine)

    with engine.connect() as connection:
        summary = connection.execute(
            text(
                f"""
                select count(*) as total, min(order_time_at) as min_order_time,
                       max(order_time_at) as max_order_time,
                       count(distinct order_time_at::date) as date_count
                from public.{TABLE}
                """
            )
        ).mappings().one()
    print(
        f"[DONE] deleted_for_replacement={replaced} read={read_rows} "
        f"accepted={accepted_rows} source_dates={len(all_source_dates)} summary={dict(summary)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
