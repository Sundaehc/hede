from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.vip_schema import VIP_DAILY_SNAPSHOT_TABLE
from domain.vip_sources import VIP_DAILY_COLUMN_ALIASES
from storage.date_normalization import parse_date_range


def prepare_snapshot_rows(rows: list[dict], snapshot_date: date) -> list[dict]:
    by_goods_id = {}
    for row in rows:
        goods_id = str(row.get("goods_id") or "").strip()
        if not goods_id:
            continue
        start_date, end_date = parse_date_range(row.get("date"))
        if start_date != snapshot_date or end_date != snapshot_date:
            raise ValueError(f"Source row {row.get('source_row_number')} has date {row.get('date')!r}, expected {snapshot_date}")
        record = {
            **row, "goods_id": goods_id, "snapshot_date": snapshot_date,
            "report_type": "罗盘", "period": "1d", "date_range": str(row["date"]),
            "report_start_date": start_date, "report_end_date": end_date,
        }
        if goods_id in by_goods_id:
            raise ValueError(f"Duplicate goods_id {goods_id} in source file")
        by_goods_id[goods_id] = record
    return list(by_goods_id.values())


def backfill_snapshot_file(repository, file_path: Path, snapshot_date: date, *, execute: bool = False) -> dict:
    if "日罗盘" not in file_path.stem:
        raise ValueError("Only daily compass reports can be used for snapshot backfill")
    rows = prepare_snapshot_rows(repository._read_excel(file_path, VIP_DAILY_COLUMN_ALIASES), snapshot_date)
    result = {"source_file": str(file_path), "snapshot_date": snapshot_date.isoformat(), "source_rows": len(rows), "inserted": 0, "inserted_ids": []}
    if execute and rows:
        with repository.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '60s'")
            for start in range(0, len(rows), 500):
                statement = pg_insert(VIP_DAILY_SNAPSHOT_TABLE).values(rows[start:start + 500]).on_conflict_do_nothing(
                    index_elements=["snapshot_date", "goods_id"],
                ).returning(VIP_DAILY_SNAPSHOT_TABLE.c.id)
                result["inserted_ids"].extend(connection.execute(statement).scalars())
            result["inserted"] = len(result["inserted_ids"])
    return result
