"""Replace order history from desktop exports while preserving current rows.

The desktop folders contain historical exports captured before today's daily
imports.  Each target table is rebuilt as the union of those exports and the
current database snapshot, with current rows winning natural-key conflicts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import md5
import json
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import load_settings
from domain.dewu_order_schema import DEWU_ORDERS_TABLE
from domain.vip_sources import JST_AFTERSALE_RETURN_COLUMN_ALIASES
from storage.dewu_order_repository import DewuOrderSource, parse_dewu_order_workbook
from storage.vip_repository import VipRepository, _xlsx_sheet_rows


AFTERSALE_STAGE = "jst_aftersale_returns_desktop_stage"
AFTERSALE_BACKUP = "jst_aftersale_returns_before_desktop_import"
DEWU_STAGE = "dewu_orders_desktop_stage"
DEWU_BACKUP = "dewu_orders_before_desktop_import"

AFTERSALE_DATA_COLUMNS = (
    "source_workbook",
    "source_sheet",
    "source_row_number",
    "raw_payload",
    "original_goods_code",
    "returned_qty",
    "application_date_value",
    "order_date",
    "order_time",
    "platform_site",
    "shop_name",
    "online_order_id",
    "order_date_value",
    "order_time_value",
    "extra_fields",
)

AFTERSALE_NUMBER = "\u552e\u540e\u5355\u53f7"
AFTERSALE_APPLICATION_DATE = "\u7533\u8bf7\u65e5\u671f"
AFTERSALE_REGISTRATION_TIME = "\u767b\u8bb0\u65f6\u95f4"
AFTERSALE_SUB_ORDER = "\u7ebf\u4e0a\u5b50\u8ba2\u5355\u7f16\u53f7"
AFTERSALE_PRODUCT_CODE = "\u5546\u54c1\u7f16\u7801"


def _key(*values: object) -> str:
    material = "\x1f".join(str(value or "").strip() for value in values)
    return md5(material.encode("utf-8"), usedforsecurity=False).hexdigest()


def _files(root: Path) -> list[Path]:
    files = sorted(
        (path for path in root.glob("*.xlsx") if not path.name.startswith("~$")),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {root}")
    return files


def _brand_from_name(value: object) -> tuple[str, str]:
    name = str(value or "").strip()
    upper = name.upper()
    if "C.BANNER" in upper or "C\u00b0BANNER" in upper or "\u5343\u767e\u5ea6" in name:
        return "cbanner", "\u5343\u767e\u5ea6"
    if "EBLAN" in upper or "\u4f0a\u4f34" in name:
        return "eblan", "\u4f0a\u4f34"
    if "TRUMPPIPE" in upper or "\u70df\u6597" in name:
        return "yandou", "\u70df\u6597"
    if "SMILEY" in upper or "\u7b11\u8138" in name:
        return "smiley", "\u7b11\u8138"
    raise ValueError(f"Unsupported Dewu brand: {name!r}")


def _drop_and_create_stage(connection, *, target: str, stage: str, key_sql: str) -> None:
    connection.execute(text(f"DROP TABLE IF EXISTS public.{stage}"))
    connection.execute(
        text(
            f"CREATE UNLOGGED TABLE public.{stage} "
            f"(LIKE public.{target} INCLUDING DEFAULTS INCLUDING GENERATED "
            "EXCLUDING IDENTITY EXCLUDING CONSTRAINTS EXCLUDING INDEXES)"
        )
    )
    connection.execute(text(f"ALTER TABLE public.{stage} DROP COLUMN id"))
    connection.execute(text(f"ALTER TABLE public.{stage} ADD COLUMN record_key TEXT"))
    connection.execute(text(f"ALTER TABLE public.{stage} ADD PRIMARY KEY (record_key)"))


def _create_backup(
    connection,
    *,
    target: str,
    backup: str,
    key_sql: str,
    where_sql: str,
    parameters: dict[str, object],
) -> int:
    connection.execute(text(f"DROP TABLE IF EXISTS public.{backup}"))
    connection.execute(
        text(
            f"CREATE UNLOGGED TABLE public.{backup} AS "
            f"SELECT * FROM public.{target} WHERE {where_sql}"
        ),
        parameters,
    )
    connection.execute(text(f"ALTER TABLE public.{backup} ADD COLUMN record_key TEXT"))
    connection.execute(text(f"UPDATE public.{backup} SET record_key = {key_sql}"))
    connection.execute(text(f"CREATE UNIQUE INDEX ON public.{backup} (record_key)"))
    return int(connection.execute(text(f"SELECT count(*) FROM public.{backup}")).scalar_one())


def _reflect(engine, table_name: str) -> Table:
    return Table(table_name, MetaData(), autoload_with=engine)


def import_dewu(engine, source_root: Path, preserve_date: date) -> dict[str, object]:
    files = _files(source_root)
    backup_key_sql = "md5(coalesce(order_number, ''))"
    with engine.begin() as connection:
        DEWU_ORDERS_TABLE.create(connection, checkfirst=True)
        protected_count = _create_backup(
            connection,
            target="dewu_orders",
            backup=DEWU_BACKUP,
            key_sql=backup_key_sql,
            where_sql="order_date >= :preserve_date",
            parameters={"preserve_date": preserve_date},
        )
        _drop_and_create_stage(
            connection,
            target="dewu_orders",
            stage=DEWU_STAGE,
            key_sql=backup_key_sql,
        )

    stage_table = _reflect(engine, DEWU_STAGE)
    counts: Counter[str] = Counter()
    date_min: date | None = None
    date_max: date | None = None
    skipped_today = 0
    skipped_invalid_date = 0

    for source_file in files:
        source = DewuOrderSource("desktop", "desktop", source_file.name)
        parsed = parse_dewu_order_workbook(source_file, source)
        payload: list[dict[str, object]] = []
        for row in parsed:
            brand_group, brand_label = _brand_from_name(row.get("brand_name"))
            row["brand_group"] = brand_group
            row["brand_label"] = brand_label
            order_date = row.get("order_date")
            if not isinstance(order_date, date):
                skipped_invalid_date += 1
                continue
            if order_date >= preserve_date:
                skipped_today += 1
                continue
            date_min = order_date if date_min is None else min(date_min, order_date)
            date_max = order_date if date_max is None else max(date_max, order_date)
            counts[brand_group] += 1
            row["record_key"] = _key(row.get("order_number"))
            payload.append(row)

        update_columns = {
            column.name: getattr(pg_insert(stage_table).excluded, column.name)
            for column in stage_table.columns
            if column.name not in {"record_key", "created_at", "updated_at"}
        }
        with engine.begin() as connection:
            for offset in range(0, len(payload), 500):
                statement = (
                    pg_insert(stage_table)
                    .values(payload[offset : offset + 500])
                    .on_conflict_do_update(
                        index_elements=[stage_table.c.record_key],
                        set_=update_columns,
                    )
                )
                connection.execute(statement)
        print(f"[DEWU] {source_file.name}: parsed={len(parsed)} staged={len(payload)}", flush=True)

    target_columns = [column.name for column in DEWU_ORDERS_TABLE.columns if column.name != "id"]
    columns_sql = ", ".join(target_columns)
    with engine.begin() as connection:
        staged_before = int(connection.execute(text(f"SELECT count(*) FROM {DEWU_STAGE}")).scalar_one())
        overlaps = int(
            connection.execute(
                text(
                    f"SELECT count(*) FROM {DEWU_STAGE} stage "
                    f"JOIN {DEWU_BACKUP} backup USING (record_key)"
                )
            ).scalar_one()
        )
        connection.execute(
            text(
                f"DELETE FROM {DEWU_STAGE} stage USING {DEWU_BACKUP} backup "
                "WHERE stage.record_key = backup.record_key"
            )
        )
        connection.execute(text("DELETE FROM dewu_orders"))
        connection.execute(
            text(f"INSERT INTO dewu_orders ({columns_sql}) SELECT {columns_sql} FROM {DEWU_STAGE}")
        )
        connection.execute(
            text(f"INSERT INTO dewu_orders ({columns_sql}) SELECT {columns_sql} FROM {DEWU_BACKUP}")
        )
        final_count = int(connection.execute(text("SELECT count(*) FROM dewu_orders")).scalar_one())
        protected_missing = int(
            connection.execute(
                text(
                    f"SELECT count(*) FROM {DEWU_BACKUP} backup "
                    "LEFT JOIN dewu_orders target ON target.order_number = backup.order_number "
                    "WHERE target.id IS NULL"
                )
            ).scalar_one()
        )
        if protected_missing:
            raise RuntimeError(f"Dewu protected-row validation failed: {protected_missing} rows missing")

    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE {DEWU_STAGE}"))
        connection.execute(text(f"DROP TABLE {DEWU_BACKUP}"))

    return {
        "files": len(files),
        "staged": staged_before,
        "overlaps_kept_from_current": overlaps,
        "protected_current": protected_count,
        "final": final_count,
        "date_min": date_min,
        "date_max": date_max,
        "counts": dict(counts),
        "skipped_today": skipped_today,
        "skipped_invalid_date": skipped_invalid_date,
    }


def _map_aftersale_row(
    repository: VipRepository,
    *,
    headers: dict[int, str],
    values: dict[int, str],
    source_file: Path,
    row_number: int,
) -> tuple[dict[str, object] | None, date | None]:
    raw = {header: values.get(index, "") for index, header in headers.items()}
    mapped: dict[str, object] = {}
    original_values: dict[str, object] = {}
    for index, header in headers.items():
        column = JST_AFTERSALE_RETURN_COLUMN_ALIASES.get(header)
        if not column:
            continue
        value = values.get(index, "")
        original_values[column] = value
        mapped[column] = (
            repository._cell_int(value)
            if column == "returned_qty"
            else repository._cell_text(value)
        )

    original_code = str(mapped.get("original_goods_code") or "").strip()
    returned_qty = repository._cell_int(mapped.get("returned_qty"))
    if not original_code or returned_qty <= 0:
        return None, None

    application_date = repository._parse_excel_date(
        raw.get(AFTERSALE_APPLICATION_DATE) or raw.get(AFTERSALE_REGISTRATION_TIME)
    )
    aftersale_number = raw.get(AFTERSALE_NUMBER)
    sub_order = raw.get(AFTERSALE_SUB_ORDER)
    product_code = raw.get(AFTERSALE_PRODUCT_CODE)
    if not str(aftersale_number or "").strip() or not str(product_code or "").strip():
        record_key = _key(source_file.name, row_number)
    else:
        record_key = _key(aftersale_number, sub_order, product_code)

    raw_payload = {
        key: repository._json_cell_value(value)
        for key, value in raw.items()
    }
    record: dict[str, object] = {
        "record_key": record_key,
        "application_date": application_date,
        "source_workbook": source_file.stem,
        "source_sheet": "Sheet1",
        "source_row_number": str(row_number),
        "raw_payload": raw_payload,
        "original_goods_code": original_code,
        "returned_qty": returned_qty,
        "application_date_value": application_date,
        "order_date": mapped.get("order_date"),
        "order_time": mapped.get("order_time"),
        "platform_site": mapped.get("platform_site"),
        "shop_name": mapped.get("shop_name"),
        "online_order_id": mapped.get("online_order_id"),
        "order_date_value": repository._parse_excel_date(
            original_values.get("order_date") or mapped.get("order_date")
        ),
        "order_time_value": repository._parse_excel_date(
            original_values.get("order_time") or mapped.get("order_time")
        ),
        "extra_fields": None,
    }
    return record, application_date


def _create_aftersale_tables(engine, preserve_date: date) -> int:
    backup_key_sql = (
        "md5(concat("
        f"btrim(coalesce(raw_payload ->> '{AFTERSALE_NUMBER}', '')), chr(31), "
        f"btrim(coalesce(raw_payload ->> '{AFTERSALE_SUB_ORDER}', '')), chr(31), "
        f"btrim(coalesce(raw_payload ->> '{AFTERSALE_PRODUCT_CODE}', ''))))"
    )
    with engine.begin() as connection:
        protected_count = _create_backup(
            connection,
            target="jst_aftersale_returns",
            backup=AFTERSALE_BACKUP,
            key_sql=backup_key_sql,
            where_sql=(
                "source_workbook = :daily_source "
                "AND created_at::date >= :preserve_date"
            ),
            parameters={
                "daily_source": "\u552e\u540e\uff08\u9000\u8d27\u9000\u6b3e\uff09",
                "preserve_date": preserve_date,
            },
        )
        connection.execute(text(f"DROP TABLE IF EXISTS public.{AFTERSALE_STAGE}"))
        connection.execute(
            text(
                f"CREATE UNLOGGED TABLE public.{AFTERSALE_STAGE} ("
                "record_key TEXT PRIMARY KEY, application_date DATE, "
                "source_workbook TEXT NOT NULL, source_sheet TEXT NOT NULL, "
                "source_row_number TEXT NOT NULL, raw_payload JSON NOT NULL, "
                "original_goods_code TEXT, returned_qty INTEGER, "
                "application_date_value DATE, order_date TEXT, "
                "order_time TEXT, platform_site TEXT, shop_name TEXT, online_order_id TEXT, "
                "order_date_value DATE, order_time_value DATE, extra_fields JSON)"
            )
        )
    return protected_count


def _stage_aftersale_file(
    engine,
    repository: VipRepository,
    source_file: Path,
    preserve_date: date,
) -> dict[str, object]:
    iterator = _xlsx_sheet_rows(source_file)
    try:
        _, header_values = next(iterator)
    except StopIteration:
        return {"read": 0, "staged": 0, "skipped": 0, "skipped_today": 0}
    headers = {index: value for index, value in header_values.items() if value}
    mapped_columns = {
        JST_AFTERSALE_RETURN_COLUMN_ALIASES.get(header)
        for header in headers.values()
    }
    required = {"original_goods_code", "returned_qty", "order_date"}
    if not required.issubset(mapped_columns):
        raise ValueError(f"{source_file.name} missing required aftersale columns")

    stage_columns = ("record_key", "application_date", *AFTERSALE_DATA_COLUMNS)
    read_rows = 0
    staged_rows = 0
    skipped_rows = 0
    skipped_today = 0
    min_application: date | None = None
    max_application: date | None = None
    min_order: date | None = None
    max_order: date | None = None

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS aftersale_file_stage"))
        connection.execute(
            text(
                f"CREATE TEMP TABLE aftersale_file_stage "
                f"(LIKE public.{AFTERSALE_STAGE} INCLUDING DEFAULTS "
                "EXCLUDING CONSTRAINTS EXCLUDING INDEXES) ON COMMIT DROP"
            )
        )
        driver = connection.connection.driver_connection
        copy_sql = (
            "COPY aftersale_file_stage ("
            + ", ".join(stage_columns)
            + ") FROM STDIN"
        )
        with driver.cursor().copy(copy_sql) as copy:
            for row_number, values in iterator:
                read_rows += 1
                record, application_date = _map_aftersale_row(
                    repository,
                    headers=headers,
                    values=values,
                    source_file=source_file,
                    row_number=row_number,
                )
                if record is None:
                    skipped_rows += 1
                    continue
                if application_date is not None and application_date >= preserve_date:
                    skipped_today += 1
                    continue
                order_date = record.get("order_date_value") or record.get("order_time_value")
                if isinstance(application_date, date):
                    min_application = application_date if min_application is None else min(min_application, application_date)
                    max_application = application_date if max_application is None else max(max_application, application_date)
                if isinstance(order_date, date):
                    min_order = order_date if min_order is None else min(min_order, order_date)
                    max_order = order_date if max_order is None else max(max_order, order_date)
                values_to_copy = [record[column] for column in stage_columns]
                raw_index = stage_columns.index("raw_payload")
                values_to_copy[raw_index] = json.dumps(
                    values_to_copy[raw_index],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                copy.write_row(tuple(values_to_copy))
                staged_rows += 1
                if staged_rows % 100_000 == 0:
                    print(f"[AFTERSALE] {source_file.name}: staged={staged_rows}", flush=True)

        columns_sql = ", ".join(stage_columns)
        updates_sql = ", ".join(
            f"{column}=excluded.{column}"
            for column in stage_columns
            if column != "record_key"
        )
        connection.execute(
            text(
                f"INSERT INTO public.{AFTERSALE_STAGE} ({columns_sql}) "
                f"SELECT DISTINCT ON (record_key) {columns_sql} "
                "FROM aftersale_file_stage "
                "ORDER BY record_key, source_row_number::bigint DESC "
                "ON CONFLICT (record_key) DO UPDATE SET "
                f"{updates_sql}"
            )
        )

    return {
        "read": read_rows,
        "staged": staged_rows,
        "skipped": skipped_rows,
        "skipped_today": skipped_today,
        "application_min": min_application,
        "application_max": max_application,
        "order_min": min_order,
        "order_max": max_order,
    }


def import_aftersale(engine, source_root: Path, preserve_date: date) -> dict[str, object]:
    files = _files(source_root)
    repository = VipRepository(str(engine.url))
    protected_count = _create_aftersale_tables(engine, preserve_date)
    details: dict[str, dict[str, object]] = {}
    for source_file in files:
        result = _stage_aftersale_file(engine, repository, source_file, preserve_date)
        details[source_file.name] = result
        print(f"[AFTERSALE] {source_file.name}: {result}", flush=True)

    target_columns = ", ".join(AFTERSALE_DATA_COLUMNS)
    with engine.begin() as connection:
        staged_before = int(connection.execute(text(f"SELECT count(*) FROM {AFTERSALE_STAGE}")).scalar_one())
        overlaps = int(
            connection.execute(
                text(
                    f"SELECT count(*) FROM {AFTERSALE_STAGE} stage "
                    f"JOIN {AFTERSALE_BACKUP} backup USING (record_key)"
                )
            ).scalar_one()
        )
        connection.execute(
            text(
                f"DELETE FROM {AFTERSALE_STAGE} stage USING {AFTERSALE_BACKUP} backup "
                "WHERE stage.record_key = backup.record_key"
            )
        )
        connection.execute(text("DELETE FROM jst_aftersale_returns"))
        connection.execute(
            text(
                f"INSERT INTO jst_aftersale_returns ({target_columns}) "
                f"SELECT {target_columns} FROM {AFTERSALE_STAGE}"
            )
        )
        connection.execute(
            text(
                f"INSERT INTO jst_aftersale_returns ({target_columns}, created_at, updated_at) "
                f"SELECT {target_columns}, created_at, updated_at FROM {AFTERSALE_BACKUP}"
            )
        )
        final_count = int(connection.execute(text("SELECT count(*) FROM jst_aftersale_returns")).scalar_one())
        protected_missing = int(
            connection.execute(
                text(
                    f"SELECT count(*) FROM {AFTERSALE_BACKUP} backup "
                    "LEFT JOIN jst_aftersale_returns target ON "
                    f"md5(concat(btrim(coalesce(target.raw_payload ->> '{AFTERSALE_NUMBER}', '')), "
                    f"chr(31), btrim(coalesce(target.raw_payload ->> '{AFTERSALE_SUB_ORDER}', '')), "
                    f"chr(31), btrim(coalesce(target.raw_payload ->> '{AFTERSALE_PRODUCT_CODE}', '')))) "
                    "= backup.record_key "
                    "WHERE target.id IS NULL"
                )
            ).scalar_one()
        )
        if protected_missing:
            raise RuntimeError(f"Aftersale protected-row validation failed: {protected_missing} rows missing")

    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE {AFTERSALE_STAGE}"))
        connection.execute(text(f"DROP TABLE {AFTERSALE_BACKUP}"))

    return {
        "files": len(files),
        "staged": staged_before,
        "overlaps_kept_from_current": overlaps,
        "protected_current": protected_count,
        "final": final_count,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import desktop aftersale and Dewu order history")
    parser.add_argument("--target", choices=("all", "dewu", "aftersale"), default="all")
    parser.add_argument(
        "--dewu-root",
        type=Path,
        default=Path.home() / "Desktop" / "\u5f97\u7269\u8ba2\u5355",
    )
    parser.add_argument(
        "--aftersale-root",
        type=Path,
        default=Path.home() / "Desktop" / "\u552e\u540e",
    )
    parser.add_argument("--preserve-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)

    if args.target in {"all", "dewu"}:
        print("[DEWU] starting desktop history replacement", flush=True)
        print(import_dewu(engine, args.dewu_root, args.preserve_date), flush=True)
    if args.target in {"all", "aftersale"}:
        print("[AFTERSALE] starting desktop history replacement", flush=True)
        print(import_aftersale(engine, args.aftersale_root, args.preserve_date), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
