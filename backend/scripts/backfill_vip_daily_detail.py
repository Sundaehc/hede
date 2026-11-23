"""Refresh source fields on existing VIP daily-sales rows."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import date
from functools import lru_cache
import gzip
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy import create_engine, text

from config import load_settings
from domain.daily_sales_schema import VIP_DAILY_BASE_FIELDS
from domain.vip_daily_detail import VIP_DAILY_DETAIL_FIELDS, migrate_vip_daily_detail
from storage.daily_sales_repository import _header, _key_text, _vip_base_value, _vip_detail_value
from storage.date_normalization import parse_date
from storage.vip_repository import _xlsx_sheet_rows


FIELD_GROUPS = {"detail": VIP_DAILY_DETAIL_FIELDS, "base": VIP_DAILY_BASE_FIELDS}
KEYS = ("sales_date", "goods_id", "size_id")
DATE_NAME = re.compile(r"\d{4}-\d{2}-\d{2}")


def _extract(task: tuple[Path, Path, str]) -> tuple[str, int, int]:
    source, output, group = task
    field_specs = FIELD_GROUPS[group]
    parse_value = _vip_base_value if group == "base" else _vip_detail_value
    expected = date.fromisoformat(source.stem)
    positions: set[int] = set()
    parse_day = lru_cache(maxsize=16)(parse_date)
    temporary = output.with_name(f"{output.name}.{uuid4().hex}.tmp")
    count = duplicates = 0
    seen = {}
    try:
        with gzip.open(temporary, "wt", encoding="utf-8", newline="", compresslevel=3) as stream:
            writer = csv.writer(stream, lineterminator="\n")
            rows = _xlsx_sheet_rows(source, positions)
            try:
                _, values = next(rows)
                header_index = {_header(value): index for index, value in values.items()}
                required = ("日期", "商品ID", "SIZE_ID", *(header for _, header, _ in field_specs))
                missing = set(required).difference(header_index)
                if missing:
                    raise ValueError(f"missing headers: {', '.join(sorted(missing))}")
                positions.update(header_index[header] for header in required)
                date_index, goods_index, size_index = (header_index[h] for h in required[:3])
                metrics = [(name, header_index[header], kind) for name, header, kind in field_specs]
                for row_number, row in rows:
                    if not any(row.values()):
                        continue
                    sales_date = parse_day(row.get(date_index, ""))
                    goods_id, size_id = _key_text(row.get(goods_index)), _key_text(row.get(size_index))
                    if sales_date != expected or not goods_id:
                        raise ValueError(f"row {row_number}: invalid date or missing goods ID")
                    try:
                        detail = tuple(parse_value(name, row.get(index), kind, strict=True)
                                       for name, index, kind in metrics)
                    except ValueError as error:
                        raise ValueError(f"row {row_number}: {error}") from error
                    key = (goods_id, size_id)
                    if key in seen:
                        if seen[key] != detail:
                            raise ValueError(f"row {row_number}: conflicting duplicate business key")
                        duplicates += 1
                        continue
                    seen[key] = detail
                    writer.writerow((source.stem, goods_id, size_id, *detail))
                    count += 1
            finally:
                rows.close()
        if not count:
            raise ValueError("no data rows")
        temporary.replace(output)
    except (ValueError, OSError, StopIteration) as error:
        raise ValueError(f"{source.name}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)
    return source.stem, count, duplicates


def extract(source_dir: Path, stage_dir: Path, workers: int, group: str = "detail",
            date_start: date | None = None, date_end: date | None = None) -> None:
    files = sorted(p for p in source_dir.glob("*.xlsx") if DATE_NAME.fullmatch(p.stem))
    files = [path for path in files if (date_start is None or date.fromisoformat(path.stem) >= date_start)
             and (date_end is None or date.fromisoformat(path.stem) <= date_end)]
    if not files:
        raise FileNotFoundError(f"No dated workbooks: {source_dir}")
    stage_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".base.csv.gz" if group == "base" else ".csv.gz"
    tasks = [(path, stage_dir / f"{path.stem}{suffix}", group) for path in files]
    total = duplicates = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for day, rows, duplicate_rows in pool.map(_extract, tasks):
            total += rows
            duplicates += duplicate_rows
            print(f"{day}: extracted={rows} duplicate_rows={duplicate_rows}", flush=True)
    print(f"Extracted {len(tasks)} files, {total} keys, {duplicates} identical duplicates", flush=True)


def backfill(stage_dir: Path, *, apply: bool, group: str = "detail") -> None:
    field_specs = FIELD_GROUPS[group]
    fields = tuple(name for name, _, _ in field_specs)
    csv_columns = ", ".join((*KEYS, *fields))
    suffix = ".base.csv.gz" if group == "base" else ".csv.gz"
    files = sorted(p for p in stage_dir.glob(f"*{suffix}") if DATE_NAME.fullmatch(p.name.removesuffix(suffix)))
    if not files:
        raise FileNotFoundError(f"No staged workbooks: {stage_dir}")
    settings = load_settings(require_database=True)
    assert settings.database_url
    engine = create_engine(settings.database_url, hide_parameters=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        if apply and group == "detail":
            migrate_vip_daily_detail(conn)
        partitioned = conn.execute(text("SELECT to_regclass('public.vip_daily_sales') IS NOT NULL")).scalar_one()

    total = {"source": 0, "matched": 0, "different": 0, "updated": 0, "verified": 0, "db_rows": 0}
    coverage = {name: 0 for name in fields}
    changes = {name: 0 for name in fields}
    for path in files:
        day = date.fromisoformat(path.name.removesuffix(suffix))
        target = "public.vip_daily_sales" if partitioned else f"public.vip_daily_sales_{day.year:04d}"
        join = " AND ".join(f"t.{key} = s.{key}" for key in KEYS) + " AND t.sales_date = :day"
        old = ", ".join(f"t.{name}" for name in fields)
        new = ", ".join(f"s.{name}" for name in fields)
        same = f"ROW({old}) IS NOT DISTINCT FROM ROW({new})"
        with engine.begin() as conn:
            conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '180s'")
            definition = ", ".join(f"{name} {kind.compile(conn.dialect)}" for name, _, kind in field_specs)
            conn.exec_driver_sql(
                "CREATE TEMP TABLE vip_detail_stage (sales_date date NOT NULL, goods_id text NOT NULL, "
                f"size_id text NOT NULL, {definition}, PRIMARY KEY (sales_date, goods_id, size_id)) ON COMMIT DROP"
            )
            driver = conn.connection.driver_connection
            with driver.cursor() as cursor, gzip.open(path, "rb") as data:
                with cursor.copy(f"COPY vip_detail_stage ({csv_columns}) FROM STDIN WITH (FORMAT CSV, FORCE_NOT_NULL (size_id))") as copier:
                    for chunk in iter(lambda: data.read(1024 * 1024), b""):
                        copier.write(chunk)
            conn.exec_driver_sql("ANALYZE vip_detail_stage")
            source_count, wrong_day = conn.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE sales_date <> :day) FROM vip_detail_stage"
            ), {"day": day}).one()
            if wrong_day or not source_count:
                raise ValueError(f"{path.name}: empty file or contains other dates")
            db_rows = conn.execute(text(f"SELECT count(*) FROM {target} WHERE sales_date = :day"), {"day": day}).scalar_one()
            differences = ", ".join(f"count(*) FILTER (WHERE t.{name} IS DISTINCT FROM s.{name})" for name in fields)
            matched, different, *daily_changes = conn.execute(text(
                f"SELECT count(*), count(*) FILTER (WHERE NOT ({same})), {differences} "
                f"FROM vip_detail_stage s JOIN {target} t ON {join}"
            ), {"day": day}).one()
            updated = verified = 0
            daily_coverage = [0] * len(fields)
            if apply and (matched != source_count or (group == "base" and db_rows != matched)):
                raise ValueError(f"{day}: {matched} matches, {source_count} source rows, {db_rows} database rows")
            if apply:
                assignments = ", ".join(f"{name} = s.{name}" for name in fields)
                if group == "base":
                    assignments += ", updated_at = date_trunc('minute', now())"
                updated = conn.execute(text(
                    f"UPDATE {target} t SET {assignments} FROM vip_detail_stage s WHERE {join} AND NOT ({same})"
                ), {"day": day}).rowcount
                counts = ", ".join(f"count(t.{name})" for name in fields)
                verified, *daily_coverage = conn.execute(text(
                    f"SELECT count(*) FILTER (WHERE {same}), {counts} "
                    f"FROM vip_detail_stage s JOIN {target} t ON {join}"
                ), {"day": day}).one()
                if matched != verified:
                    raise RuntimeError(f"{day}: verified {verified} of {matched} matches; rolled back")
        stats = dict(source=source_count, matched=matched, different=different, updated=updated, verified=verified, db_rows=db_rows)
        for name, count in stats.items():
            total[name] += count
        for name, count, delta in zip(fields, daily_coverage, daily_changes, strict=True):
            coverage[name] += count
            changes[name] += delta
        print(day, " ".join(f"{name}={count}" for name, count in stats.items()), flush=True)
    print(f"Total days={len(files)} {total}", flush=True)
    print(f"Differences by field: {changes}", flush=True)
    if apply:
        print(f"Non-null counts for matched rows: {coverage}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    extract_args = sub.add_parser("extract")
    extract_args.add_argument("--source-dir", required=True, type=Path)
    extract_args.add_argument("--stage-dir", required=True, type=Path)
    extract_args.add_argument("--workers", type=int, default=4)
    extract_args.add_argument("--date-start", type=date.fromisoformat)
    extract_args.add_argument("--date-end", type=date.fromisoformat)
    extract_args.add_argument("--fields", choices=FIELD_GROUPS, default="detail")
    for action in ("check", "apply"):
        action_args = sub.add_parser(action)
        action_args.add_argument("--stage-dir", required=True, type=Path)
        action_args.add_argument("--fields", choices=FIELD_GROUPS, default="detail")
    args = parser.parse_args()
    if args.action == "extract":
        extract(args.source_dir, args.stage_dir, args.workers, args.fields, args.date_start, args.date_end)
    else:
        backfill(args.stage_dir, apply=args.action == "apply", group=args.fields)


if __name__ == "__main__":
    main()
