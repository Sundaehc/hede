from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock

from openpyxl import Workbook
import pytest
from sqlalchemy.dialects import postgresql

from scripts.backfill_vip_product_daily_snapshots import source_report_date
from storage.vip_daily_snapshot_backfill import backfill_snapshot_file, prepare_snapshot_rows


def test_snapshot_backfill_requires_real_report_date_not_folder_date():
    with pytest.raises(ValueError, match="expected 2026-09-11"):
        prepare_snapshot_rows([{"goods_id": "1", "date": "2025-09-11"}], date(2026, 9, 11))


def test_snapshot_backfill_rejects_missing_or_multiple_day_dates():
    for raw_date in (None, "", "2026-08-01 ~ 2026-08-02"):
        with pytest.raises(ValueError):
            prepare_snapshot_rows([{"goods_id": "1", "date": raw_date}], date(2026, 8, 2))


def test_snapshot_backfill_keeps_source_date_and_provenance():
    rows = prepare_snapshot_rows([{"goods_id": " 1 ", "date": "2026-08-02", "source_workbook": "日罗盘", "source_row_number": "2", "raw_payload": {"日期": "2026-08-02"}}], date(2026, 8, 2))
    assert rows[0]["snapshot_date"] == rows[0]["report_start_date"] == rows[0]["report_end_date"] == date(2026, 8, 2)
    assert rows[0]["goods_id"] == "1"
    assert rows[0]["raw_payload"]["日期"] == "2026-08-02"
    assert rows[0]["report_type"] == "罗盘" and rows[0]["period"] == "1d"


def test_snapshot_backfill_rejects_duplicate_ids_before_writing():
    with pytest.raises(ValueError, match="Duplicate goods_id"):
        prepare_snapshot_rows([{"goods_id": "1", "date": "2026-08-02"}] * 2, date(2026, 8, 2))


def test_snapshot_backfill_preview_never_opens_write_transaction():
    repository = Mock()
    repository._read_excel.return_value = [{"goods_id": "1", "date": "2026-08-02"}]
    result = backfill_snapshot_file(repository, Path("日罗盘.xlsx"), date(2026, 8, 2))
    assert result["source_rows"] == 1 and result["inserted"] == 0
    repository.engine.begin.assert_not_called()


def test_snapshot_backfill_only_inserts_missing_snapshots_and_never_updates_live_metrics():
    repository = MagicMock()
    repository._read_excel.return_value = [{"goods_id": "1", "date": "2026-08-02"}]
    connection = repository.engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalars.return_value = [123]
    result = backfill_snapshot_file(repository, Path("日罗盘.xlsx"), date(2026, 8, 2), execute=True)
    sql = str(connection.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert sql.startswith("INSERT INTO vip_product_daily_snapshots")
    assert "ON CONFLICT (snapshot_date, goods_id) DO NOTHING" in sql
    assert "DO UPDATE" not in sql
    assert result["inserted"] == 1
    assert result["inserted_ids"] == [123]


def test_source_report_date_comes_from_cell_not_directory(tmp_path):
    path = tmp_path / "09.12" / "日罗盘.xlsx"
    path.parent.mkdir()
    workbook = Workbook()
    workbook.active.append(["商品ID", "日期"])
    workbook.active.append(["1", "2025-09-11"])
    workbook.save(path)
    workbook.close()
    assert source_report_date(path) == date(2025, 9, 11)
