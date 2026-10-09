from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from domain.jst_monthly_order_identity import (
    deduplicate_monthly_order_rows,
    monthly_order_record_key,
    monthly_order_record_key_sql,
)
from domain.vip_schema import JST_MONTHLY_ORDERS_TABLE
from domain.vip_sources import JST_MONTHLY_ORDERS_COLUMN_ALIASES
from scripts.backfill_jst_monthly_order_keys import apply_record_key_backfill, date_window
from scripts.import_jst_monthly_orders_archive import _map_row
from storage.vip_repository import VipRepository


def order_row(**changes):
    return {
        "internal_order_id": "ORDER-1", "online_order_id": "ONLINE-1",
        "online_sub_order_id": "SUB-1", "order_time": "2026-10-01 12:30:00",
        "order_time_at": datetime(2026, 10, 1, 12, 30), "shop_name": "测试店铺",
        "style_code": "STYLE-1", "product_code": "SKU-1", "quantity": 1, "status": "已发货",
        "source_row_number": "2", "raw_payload": {"子订单编号": "INTERNAL-SUB-1"},
        **changes,
    }


@pytest.mark.parametrize("quantity", [1, "1", "1.0", Decimal("1.00")])
def test_key_normalizes_imported_quantity(quantity):
    assert monthly_order_record_key(order_row(quantity=quantity)) == monthly_order_record_key(order_row())


def test_key_preserves_internal_suborders_and_zero_quantity():
    first = order_row()
    other = order_row(raw_payload={"子订单编号": "INTERNAL-SUB-2"})
    assert monthly_order_record_key(first) != monthly_order_record_key(other)
    assert monthly_order_record_key(order_row(quantity=0)) != monthly_order_record_key(order_row(quantity=None))
    assert monthly_order_record_key(first) == monthly_order_record_key(order_row(source_row_number="30"))
    assert len(monthly_order_record_key(first)) == 64


def test_key_avoids_delimiter_collisions():
    first = order_row(internal_order_id="ORDER\x1fONLINE", online_order_id="1")
    second = order_row(internal_order_id="ORDER", online_order_id="ONLINE\x1f1")
    assert monthly_order_record_key(first) != monthly_order_record_key(second)


def test_deduplication_only_removes_identical_source_records():
    first = order_row()
    repeated = order_row(source_row_number="3")
    another = order_row(source_row_number="4", raw_payload={"子订单编号": "INTERNAL-SUB-2"})
    unique, removed = deduplicate_monthly_order_rows([first, repeated, another])
    assert removed == 1
    assert [row["source_row_number"] for row in unique] == ["3", "4"]
    assert all(row["record_key"] for row in unique)


def test_deduplication_rejects_conflicting_business_data():
    first = order_row(buyer_paid="100")
    conflict = order_row(buyer_paid="200", source_row_number="3")
    with pytest.raises(ValueError, match="业务数据不同"):
        deduplicate_monthly_order_rows([first, conflict])


def test_sql_key_rejects_untrusted_alias():
    with pytest.raises(ValueError, match="alias"):
        monthly_order_record_key_sql("orders; DROP TABLE orders")
    assert "子订单编号" in monthly_order_record_key_sql()


def test_schema_contains_time_and_key_unique_constraint():
    constraint = next(item for item in JST_MONTHLY_ORDERS_TABLE.constraints if item.name == "uq_jst_monthly_orders_order_time_record_key")
    assert [column.name for column in constraint.columns] == ["order_time_at", "record_key"]


def test_daily_import_assigns_keys_deduplicates_exact_rows_and_keeps_suborders(tmp_path, monkeypatch):
    fields = ["internal_order_id", "online_order_id", "order_time", "product_code", "quantity", "status"]
    headers = [next(header for header, field in JST_MONTHLY_ORDERS_COLUMN_ALIASES.items() if field == expected) for expected in fields]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append([*headers, "子订单编号"])
    values = ["ORDER-1", "ONLINE-1", "2026-10-01 12:30:00", "SKU-1", 1, "已发货"]
    worksheet.append([*values, "SUB-1"])
    worksheet.append([*values, "SUB-1"])
    worksheet.append([*values, "SUB-2"])
    worksheet.append([None] * (len(headers) + 1))
    source = tmp_path / "orders.xlsx"
    workbook.save(source)
    workbook.close()

    captured = []
    repository = VipRepository("sqlite://")
    monkeypatch.setattr(repository, "_batch_insert", lambda table, rows, conn: captured.extend(rows))
    monkeypatch.setattr("storage.vip_repository.ensure_annual_partitions", lambda *args: None)

    class Result:
        rowcount = 0

    class Connection:
        def execute(self, *args):
            return Result()

    class Transaction:
        def __enter__(self):
            return Connection()

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(repository.engine, "begin", lambda: Transaction())
    result = repository.import_monthly_order(source)
    assert result["imported"] == 2
    assert result["source_rows"] == 3
    assert result["duplicates_removed"] == 1
    assert len({row["record_key"] for row in captured}) == 2


def test_archive_import_uses_the_same_key_as_daily_import():
    row = order_row()
    fields = [field for field in row if field in set(JST_MONTHLY_ORDERS_COLUMN_ALIASES.values())]
    headers = {index: next(header for header, field in JST_MONTHLY_ORDERS_COLUMN_ALIASES.items() if field == expected) for index, expected in enumerate(fields)}
    values = {index: str(row[field]) for index, field in enumerate(fields)}
    headers[len(headers)] = "子订单编号"
    values[len(values)] = "INTERNAL-SUB-1"
    mapped = _map_row(headers=headers, values=values, file_path=Path("orders.xlsx"), sheet_name="Sheet1", row_number=2)
    assert mapped["record_key"] == monthly_order_record_key(row)


def test_backfill_date_window_includes_end_day():
    assert date_window(date(2026, 7, 1), date(2026, 10, 9)) == {
        "date_start": datetime(2026, 7, 1), "date_end": datetime(2026, 10, 10),
    }
    with pytest.raises(ValueError, match="结束日期"):
        date_window(date(2026, 10, 9), date(2026, 7, 1))


def test_backfill_conflicts_abort_before_backups_or_updates(monkeypatch):
    class Connection:
        statements = []

        def execute(self, statement):
            self.statements.append(str(statement))

    connection = Connection()
    monkeypatch.setattr("scripts.backfill_jst_monthly_order_keys.audit_record_keys", lambda *args: {"prospective_key_duplicates": {"groups": 1}})
    with pytest.raises(ValueError, match="冲突"):
        apply_record_key_backfill(connection, date_window(date(2026, 7, 1), date(2026, 10, 9)))
    assert connection.statements == ["LOCK TABLE public.jst_monthly_orders IN SHARE ROW EXCLUSIVE MODE"]


def test_backfill_is_idempotent_when_keys_are_present(monkeypatch):
    class Connection:
        def execute(self, statement):
            assert str(statement).startswith("LOCK TABLE")

    report = {"missing": 0, "prospective_key_duplicates": {"groups": 0}}
    monkeypatch.setattr("scripts.backfill_jst_monthly_order_keys.audit_record_keys", lambda *args: deepcopy(report))
    result = apply_record_key_backfill(Connection(), date_window(date(2026, 7, 1), date(2026, 10, 9)))
    assert result["updated"] == 0
    assert result["before"] == result["after"]


def test_backfill_backs_up_keys_before_update_and_checks_coverage(monkeypatch):
    reports = iter([
        {"missing": 2, "total": 10, "prospective_key_duplicates": {"groups": 0}},
        {"missing": 0, "total": 10, "prospective_key_duplicates": {"groups": 0}},
    ])
    monkeypatch.setattr("scripts.backfill_jst_monthly_order_keys.audit_record_keys", lambda *args: next(reports))

    class Result:
        rowcount = 2

    class Connection:
        def __init__(self):
            self.statements = []

        def execute(self, statement, parameters=None):
            self.statements.append(str(statement))
            return Result()

    connection = Connection()
    result = apply_record_key_backfill(connection, date_window(date(2026, 7, 1), date(2026, 10, 9)))
    assert result["updated"] == 2
    assert result["after"]["total"] == result["before"]["total"]
    assert "INSERT INTO public.jst_monthly_order_key_repairs" in connection.statements[2]
    assert "UPDATE public.jst_monthly_orders" in connection.statements[3]
    assert not any("DELETE" in statement for statement in connection.statements)


def test_backfill_rejects_incomplete_backup(monkeypatch):
    report = {"missing": 2, "total": 10, "prospective_key_duplicates": {"groups": 0}}
    monkeypatch.setattr("scripts.backfill_jst_monthly_order_keys.audit_record_keys", lambda *args: report)

    class Result:
        rowcount = 1

    class Connection:
        def execute(self, statement, parameters=None):
            return Result()

    with pytest.raises(RuntimeError, match="备份数量"):
        apply_record_key_backfill(Connection(), date_window(date(2026, 7, 1), date(2026, 10, 9)))
