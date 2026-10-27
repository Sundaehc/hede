from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, Mock

import psycopg
import pytest
from psycopg.errors import NumericValueOutOfRange
from psycopg.types.json import Json
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg
from sqlalchemy.exc import DataError, IntegrityError

from domain.inventory_schema import (
    INVENTORY_ACCOUNT_SUBJECT_TABLE,
    INVENTORY_DETAIL_TABLE,
    INVENTORY_TABLE,
    SUPPLIER_TABLE,
    WAREHOUSE_TABLE,
)
from storage import inventory_repository as inventory_storage
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def write_repository():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    for table in (INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_TABLE, WAREHOUSE_TABLE, INVENTORY_ACCOUNT_SUBJECT_TABLE):
        table.create(engine)
    with engine.begin() as connection:
        connection.execute(SUPPLIER_TABLE.insert().values(id=1, brand="ni", name="供应商"))
        connection.execute(WAREHOUSE_TABLE.insert().values(id=1, name="仓库"))
        connection.execute(INVENTORY_ACCOUNT_SUBJECT_TABLE.insert().values(id=1, category="费用类", name="运输费"))
    repository = object.__new__(InventoryRepository)
    repository.engine = engine
    record_ids = iter(range(1, 1000))
    repository._prepare_record = lambda record: {**InventoryRepository._prepare_record(record), "id": next(record_ids)}
    try:
        yield repository
    finally:
        engine.dispose()


def _plan(summary="导入", *, document_type="进货单", details=None, decision=None):
    return {
        "date": "2026-10-26", "document_type": document_type, "supplier": "供应商",
        "warehouse": "仓库", "handler": "测试", "summary": summary,
        "source_workbook": "test.xlsx", "source_sheet": "data", "brand": "ni", "decision": decision,
        "details": details if details is not None else [{"id": 1, "product_code": "TEST", "quantity": "2.00", "amount": "24.68"}],
    }


def test_template_buffers_details_across_documents_and_groups_totals(write_repository, monkeypatch):
    repository = write_repository
    monkeypatch.setattr(inventory_storage, "TEMPLATE_DETAIL_WRITE_BATCH_SIZE", 5)
    write = Mock(wraps=repository._insert_template_details)
    repository._insert_template_details = lambda connection, rows: write(connection, list(rows))
    statements = []
    event.listen(repository.engine, "before_cursor_execute", lambda _connection, _cursor, statement, *_args: statements.append(statement))
    plans = [
        _plan(f"单据 {index}", details=[
            {"id": index * 3 + offset + 1, "product_code": "TEST", "quantity": "2.00", "amount": "24.68"}
            for offset in range(3)
        ])
        for index in range(7)
    ]

    result = repository.import_template_documents(plans)

    assert result == {"created": 7, "replaced": 0, "skipped": 0, "details": 21}
    assert [len(call.args[1]) for call in write.call_args_list] == [5, 5, 5, 5, 1]
    assert len({row["document_id"] for row in write.call_args_list[0].args[1]}) == 2
    assert len([statement for statement in statements if statement.startswith("SELECT inventory_records.document_number")]) == 1
    assert len([statement for statement in statements if statement.startswith("UPDATE inventory_records")]) == 1
    assert not any(statement.startswith("SELECT sum(") for statement in statements)
    with repository.engine.connect() as connection:
        records = connection.execute(select(INVENTORY_TABLE).order_by(INVENTORY_TABLE.c.id)).mappings().all()
    assert [record["document_number"] for record in records] == [f"JHD-2026-10-26-{index:04d}" for index in range(1, 8)]
    assert all(record["total_count"] == Decimal("6.00") and record["amount"] == Decimal("74.04") for record in records)


def test_template_grouped_totals_preserve_return_sign_and_accounting_nulls(write_repository, monkeypatch):
    monkeypatch.setattr(inventory_storage, "TEMPLATE_TOTALS_BATCH_SIZE", 1)
    repository = write_repository
    repository.import_template_documents([
        _plan("进货"),
        _plan("退货", document_type="进货退货单", details=[
            {"id": 2, "product_code": "TEST", "quantity": "2", "amount": "24.68"},
            {"id": 3, "product_code": "TEST", "quantity": "-1", "amount": "-10"},
        ]),
        _plan("费用", document_type="应付款增加", details=[
            {"id": 4, "product_name": "运输费", "quantity": None, "amount": "-5.25"},
        ]),
        _plan("空金额", details=[{"id": 5, "product_code": "TEST", "quantity": None, "amount": None}]),
    ])

    with repository.engine.connect() as connection:
        records = {row["summary"]: row for row in connection.execute(select(INVENTORY_TABLE)).mappings()}
    assert (records["进货"]["total_count"], records["进货"]["amount"]) == (Decimal("2"), Decimal("24.68"))
    assert (records["退货"]["total_count"], records["退货"]["amount"]) == (Decimal("-1"), Decimal("-14.68"))
    assert (records["费用"]["total_count"], records["费用"]["amount"]) == (None, Decimal("-5.25"))
    assert (records["空金额"]["total_count"], records["空金额"]["amount"]) == (None, None)


@pytest.mark.parametrize("batch_size", [1, 3, 5000])
def test_template_repeated_overwrite_drops_buffered_and_written_old_details(write_repository, monkeypatch, batch_size):
    repository = write_repository
    monkeypatch.setattr(inventory_storage, "TEMPLATE_DETAIL_WRITE_BATCH_SIZE", batch_size)
    repository.import_template_documents([_plan()])
    result = repository.import_template_documents([
        _plan(decision="overwrite", details=[{"id": 2, "product_code": "FIRST", "quantity": 3, "amount": 30}]),
        _plan(decision="overwrite", details=[{"id": 2, "product_code": "LAST", "quantity": 4, "amount": 40}]),
    ])

    assert result == {"created": 0, "replaced": 2, "skipped": 0, "details": 2}
    with repository.engine.connect() as connection:
        record = connection.execute(select(INVENTORY_TABLE)).mappings().one()
        detail = connection.execute(select(INVENTORY_DETAIL_TABLE)).mappings().one()
    assert record["document_number"] == "JHD-2026-10-26-0001"
    assert (record["total_count"], record["amount"]) == (4, 40)
    assert detail["product_code"] == "LAST"


def test_template_delayed_insert_failure_rolls_back_all_documents(write_repository, monkeypatch):
    repository = write_repository
    monkeypatch.setattr(inventory_storage, "TEMPLATE_DETAIL_WRITE_BATCH_SIZE", 1)
    repository.import_template_documents([_plan()])
    plans = [
        _plan(decision="overwrite", details=[{"id": 2, "product_code": "NEW", "quantity": 1, "amount": 10}]),
        _plan("另一张", details=[{"id": 2, "product_code": "DUPLICATE", "quantity": 1, "amount": 20}]),
    ]

    with pytest.raises(IntegrityError):
        repository.import_template_documents(plans)

    with repository.engine.connect() as connection:
        record = connection.execute(select(INVENTORY_TABLE)).mappings().one()
        detail = connection.execute(select(INVENTORY_DETAIL_TABLE)).mappings().one()
    assert record["summary"] == "导入"
    assert (record["total_count"], record["amount"]) == (2, Decimal("24.68"))
    assert detail["product_code"] == "TEST"


def test_template_rejects_empty_details_before_writing_documents(write_repository):
    repository = write_repository
    with pytest.raises(ValueError, match="没有可导入的明细"):
        repository.import_template_documents([_plan(details=[])])
    with repository.engine.connect() as connection:
        assert connection.execute(select(INVENTORY_TABLE.c.id)).all() == []


def test_template_insert_keeps_heterogeneous_columns_json_and_defaults(write_repository):
    repository = write_repository
    rows = [
        {"id": 1, "document_id": 1, "product_code": "FIRST", "quantity": "2.00"},
        {"id": 2, "document_id": 1, "product_code": "SECOND", "quantity": None, "size_quantities": {"240": "2"}, "extra_fields": {"备注": "换行\n制表\t\\"}},
        {"id": 3, "document_id": 1, "product_code": "THIRD", "quantity": "1.00"},
    ]
    with repository.engine.begin() as connection:
        repository._insert_template_details(connection, rows)
    with repository.engine.connect() as connection:
        details = connection.execute(select(INVENTORY_DETAIL_TABLE).order_by(INVENTORY_DETAIL_TABLE.c.id)).mappings().all()
    assert details[0]["created_at"] is not None
    assert details[1]["quantity"] is None
    assert details[1]["size_quantities"] == {"240": "2"}
    assert details[1]["extra_fields"] == rows[1]["extra_fields"]
    assert details[2]["product_code"] == "THIRD"


def test_template_sequence_cache_is_scoped_by_prefix_and_date(write_repository):
    repository = write_repository
    with repository.engine.begin() as connection:
        connection.execute(INVENTORY_TABLE.insert(), [
            {"id": 1, "document_number": "JHD-2026-10-26-9999"},
            {"id": 2, "document_number": "JHD-2026-10-26-invalid"},
            {"id": 3, "document_number": "JHTHD-2026-10-26-0004"},
            {"id": 4, "document_number": "JHD-2026-10-27-0008"},
        ])
        sequences = {}
        assert repository._generate_document_number(connection, "2026-10-26", "进货单", sequences=sequences) == "JHD-2026-10-26-10000"
        assert repository._generate_document_number(connection, date(2026, 10, 26), "进货单", sequences=sequences) == "JHD-2026-10-26-10001"
        assert repository._generate_document_number(connection, "2026-10-26", "进货退货单", sequences=sequences) == "JHTHD-2026-10-26-0005"
        assert repository._generate_document_number(connection, "2026-10-27", "进货单", sequences=sequences) == "JHD-2026-10-27-0009"
        assert repository._generate_document_number(connection, "2026-10-26", "进货单") == "JHD-2026-10-26-10000"


def _copy_connection():
    connection = MagicMock()
    connection.dialect.name = "postgresql"
    connection.dialect.driver = "psycopg"
    return connection


def test_template_copy_preserves_json_null_and_bound_values(monkeypatch):
    monkeypatch.setattr(inventory_storage, "TEMPLATE_DETAIL_COPY_MIN_ROWS", 1)
    connection = _copy_connection()
    rows = [{"document_id": 1, "product_code": "货号\t\n\\", "quantity": None, "size_quantities": None, "extra_fields": {"颜色": "黑色"}}]

    InventoryRepository._insert_template_details(connection, rows)

    cursor = connection.connection.driver_connection.cursor.return_value.__enter__.return_value
    assert cursor.copy.call_args.args[0].as_string() == 'COPY "inventory_details" ("document_id", "product_code", "quantity", "size_quantities", "extra_fields") FROM STDIN'
    writer = cursor.copy.return_value.__enter__.return_value
    values = writer.write_row.call_args.args[0]
    assert values[:3] == (1, "货号\t\n\\", None)
    assert isinstance(values[3], Json) and values[3].obj is None
    assert isinstance(values[4], Json) and values[4].obj == {"颜色": "黑色"}
    connection.execute.assert_not_called()


@pytest.mark.parametrize("driver,row_count", [("psycopg", 1), ("psycopg2", 100)])
def test_template_copy_keeps_small_or_unsupported_batches_on_sqlalchemy(driver, row_count):
    connection = _copy_connection()
    connection.dialect.driver = driver
    InventoryRepository._insert_template_details(connection, [{"document_id": 1}] * row_count)
    connection.execute.assert_called_once()
    connection.connection.driver_connection.cursor.assert_not_called()


def test_template_copy_errors_keep_sqlstate_for_background_failure_reporting(monkeypatch):
    monkeypatch.setattr(inventory_storage, "TEMPLATE_DETAIL_COPY_MIN_ROWS", 1)
    connection = _copy_connection()
    connection.dialect = PGDialect_psycopg(dbapi=psycopg)
    cursor = connection.connection.driver_connection.cursor.return_value.__enter__.return_value
    cursor.copy.return_value.__exit__.side_effect = NumericValueOutOfRange("controlled overflow")

    with pytest.raises(DataError) as error:
        InventoryRepository._insert_template_details(connection, [{"document_id": 1, "quantity": "1e100"}])

    assert error.value.orig.sqlstate == "22003"
    assert error.value.hide_parameters is True
