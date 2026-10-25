from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import MetaData, create_engine, event, select

from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from scripts import check_inventory_product_links as checker


@pytest.fixture
def audit_connection():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "now", 0, lambda: "2026-10-25 00:30:00",
    ))
    metadata = MetaData()
    for source in (PRODUCT_ARCHIVE_IDENTITY_TABLE, INVENTORY_TABLE, INVENTORY_DETAIL_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE):
        source.to_metadata(metadata).create(engine)
    with engine.begin() as connection:
        connection.execute(SUPPLIER_BRAND_TABLE.insert(), [
            {"id": 1, "code": "ns", "name": "NS"},
            {"id": 2, "code": "hejin", "name": "千百度赫锦"},
        ])
        connection.execute(SUPPLIER_TABLE.insert(), [{"id": 1, "name": "NS工厂", "brand": "ns"}])
        connection.execute(PRODUCT_ARCHIVE_IDENTITY_TABLE.insert(), [
            {"id": 11, "brand": "ns", "source_table": "archive_ns", "source_product_id": 11,
             "sku": "SKU-1", "original_sku": "STYLE", "is_active": True},
            {"id": 12, "brand": "ns", "source_table": "archive_ns", "source_product_id": 12,
             "sku": "SKU-1", "original_sku": "STYLE", "is_active": False},
            {"id": 13, "brand": "hejin", "source_table": "archive_hejin", "source_product_id": 13,
             "sku": "SKU-1", "original_sku": "STYLE", "is_active": True},
            {"id": 14, "brand": "ns", "source_table": "archive_ns", "source_product_id": 14,
             "sku": "RENAMED-SKU", "original_sku": "RENAMED-STYLE", "is_active": True},
            {"id": 15, "brand": "ns", "source_table": "archive_ns", "source_product_id": 15,
             "sku": "SKU-2", "original_sku": "STYLE", "is_active": True},
        ])
        yield connection
    engine.dispose()


def add_detail(connection, *, detail_id=1, identity_id=11, code="SKU-1", brand="ns", document_type="进货订单", deleted=False, supplier=""):
    connection.execute(INVENTORY_TABLE.insert().values(
        id=detail_id, document_number=f"DOC-{detail_id}", document_type=document_type,
        supplier=supplier, raw_payload={"brand": brand}, deleted_at=datetime(2026, 10, 25) if deleted else None,
    ))
    connection.execute(INVENTORY_DETAIL_TABLE.insert().values(
        id=detail_id, document_id=detail_id, product_code=code,
        product_identity_id=identity_id, quantity=60, unit_price=268, amount=16080,
    ))


@pytest.mark.parametrize("identity_id,code,brand,document_type,expected", [
    (None, "SKU-1", "ns", "进货订单", "unlinked"),
    (999, "SKU-1", "ns", "进货订单", "missing_identity"),
    (12, "SKU-1", "ns", "进货订单", "inactive_identity"),
    (13, "SKU-1", "ns", "进货订单", "brand_mismatch"),
    (14, "OLD-SKU", "ns", "进货订单", "purchase_code_mismatch"),
    (11, "SKU-1", "NS", "进货订单", None),
    (13, "SKU-1", "千百度赫锦", "进货订单", None),
    (14, "OLD-SKU", "ns", "进货单", None),
    (14, "OLD-SKU", "ns", "进货退货单", None),
    (11, "SKU-1", "ns", "进货订单", None),
])
def test_classifies_links_without_overwriting_historical_codes(audit_connection, identity_id, code, brand, document_type, expected):
    add_detail(audit_connection, identity_id=identity_id, code=code, brand=brand, document_type=document_type)
    report = checker.collect_report(audit_connection)
    assert report["checked_product_details"] == 1
    assert report["issue_count"] == (1 if expected else 0)
    assert [row["issue_type"] for row in report["samples"]] == ([expected] if expected else [])


@pytest.mark.parametrize("options", [
    {"code": ""}, {"code": "  "}, {"code": None}, {"deleted": True}, {"document_type": "应付款增加"},
])
def test_excludes_deleted_blank_and_accounting_details(audit_connection, options):
    add_detail(audit_connection, identity_id=None, **options)
    report = checker.collect_report(audit_connection)
    assert report["checked_product_details"] == 0
    assert report["issue_count"] == 0


def test_candidates_stay_in_brand_and_ambiguity_is_reported(audit_connection):
    add_detail(audit_connection, identity_id=12)
    add_detail(audit_connection, detail_id=2, identity_id=None, code="STYLE")
    add_detail(audit_connection, detail_id=3, identity_id=None, brand="")
    add_detail(audit_connection, detail_id=4, identity_id=None, brand="", supplier="NS工厂")
    samples = {row["detail_id"]: row for row in checker.collect_report(audit_connection)["samples"]}
    assert samples[1]["candidate_count"] == 1
    assert samples[1]["candidates"][0]["id"] == 11
    assert samples[2]["candidate_count"] == 2
    assert samples[2]["candidate_status"] == "存在多个候选，禁止自动关联"
    assert samples[3]["candidate_count"] == 0
    assert samples[3]["candidate_status"] == "品牌不明确，需人工确认"
    assert samples[4]["candidate_brand"] == "ns"
    assert samples[4]["candidate_count"] == 1


def test_counts_are_complete_when_examples_are_limited(audit_connection):
    for detail_id in range(1, 5):
        add_detail(audit_connection, detail_id=detail_id, identity_id=None)
    add_detail(audit_connection, detail_id=5, identity_id=12)
    report = checker.collect_report(audit_connection, sample_limit=1)
    assert report["issue_count"] == 5
    assert report["counts_by_issue"] == {"未关联商品档案": 4, "关联档案已失效": 1}
    assert report["samples_truncated"] is True
    assert len(report["samples"]) == 2


def test_check_only_issues_selects_and_leaves_prices_and_links_unchanged(audit_connection):
    add_detail(audit_connection, identity_id=12)
    before = [dict(row) for row in audit_connection.execute(select(INVENTORY_DETAIL_TABLE)).mappings()]
    statements = []
    event.listen(audit_connection, "before_cursor_execute", lambda _connection, _cursor, statement, *_args: statements.append(statement))
    checker.collect_report(audit_connection)
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert [dict(row) for row in audit_connection.execute(select(INVENTORY_DETAIL_TABLE)).mappings()] == before


def test_production_audit_uses_read_only_consistent_snapshot(monkeypatch):
    engine = MagicMock()
    connection = engine.connect.return_value.execution_options.return_value.__enter__.return_value
    collect = Mock(return_value={"issue_count": 0})
    monkeypatch.setattr(checker, "collect_report", collect)
    assert checker.check_links(engine) == {"issue_count": 0}
    engine.connect.return_value.execution_options.assert_called_once_with(isolation_level="REPEATABLE READ")
    assert str(connection.execute.call_args_list[0].args[0]) == "SET TRANSACTION READ ONLY"
    collect.assert_called_once_with(connection, sample_limit=100)


@pytest.mark.parametrize("issue_count,expected_exit", [(0, 0), (2, 1)])
def test_main_saves_report_and_returns_failure_for_issues(monkeypatch, tmp_path, issue_count, expected_exit):
    engine = Mock()
    monkeypatch.setattr(checker, "load_settings", lambda **_kwargs: SimpleNamespace(database_url="test-only"))
    monkeypatch.setattr(checker, "create_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(checker, "check_links", lambda *_args, **_kwargs: {
        "issue_count": issue_count, "checked_product_details": 3,
        "counts_by_issue": {"关联档案已失效": issue_count} if issue_count else {},
        "notice": "只读检查，不改价",
    })
    assert checker.main(["--output-dir", str(tmp_path)]) == expected_exit
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["issue_count"] == issue_count
    assert len(list(tmp_path.glob("check-*.json"))) == 1
    engine.dispose.assert_called_once()


def test_invalid_sample_limit_is_rejected():
    with pytest.raises(SystemExit):
        checker.main(["--sample-limit", "0"])


def test_daily_wrapper_records_runs_and_uses_read_only_checker():
    scripts = Path(checker.__file__).parent
    wrapper = (scripts / "check_inventory_product_links_daily.cmd").read_text(encoding="utf-8")
    assert "scripts.run_scheduled_task" in wrapper
    assert '--task-name "HedeCheckInventoryProductLinksDaily"' in wrapper
    assert "scripts.check_inventory_product_links" in wrapper
    assert "--execute" not in wrapper
    configuration = (scripts / "configure_inventory_product_links_task.ps1").read_text(encoding="utf-8")
    assert ".AddMinutes(30)" in configuration
    assert "-Daily" in configuration
    assert "-UserId 'SYSTEM' -LogonType ServiceAccount" in configuration
    assert "-StartWhenAvailable" in configuration
    assert "-MultipleInstances IgnoreNew" in configuration
