from datetime import date
import json
import os
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from domain.inventory_schema import SUPPLIER_BRAND_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.task_status_schema import SCHEDULED_TASK_STATUS_TABLE
from scripts import check_stock_quality_reports_daily as audit
from storage.product_repository import ProductRepository
from storage.stock_quality_reports import SUMMARY_DIR, StockQualityReports
from storage.task_status_repository import ScheduledTaskStatusRepository


def _workbook(root, name, rows):
    workbook = Workbook()
    workbook.active.title = "报告"
    workbook.active.append(["原始货号", "检查结果"])
    for row in rows:
        workbook.active.append(row)
    workbook.save(root / SUMMARY_DIR / name)
    workbook.close()


def test_audit_uses_product_matching_and_reports_specific_source_rows(tmp_path):
    (tmp_path / SUMMARY_DIR).mkdir()
    (tmp_path / "历史").mkdir()
    _workbook(tmp_path, "千百度质检表格汇总.xlsx", [
        ("shoe001", "甲.pdf\n旧名_3026057788\n缺少.pdf\n冲突.pdf"),
        ("ONLY-FOREIGN", "其他.pdf"),
        (None, "无货号.pdf"),
        ("SHOE002", None),
    ])
    (tmp_path / "甲.pdf").write_bytes(b"matched")
    (tmp_path / "改名_3026057788.pdf").write_bytes(b"number match")
    (tmp_path / "冲突.pdf").write_bytes(b"file 1")
    (tmp_path / "历史" / "冲突.pdf").write_bytes(b"file 2")
    (tmp_path / SUMMARY_DIR / "正在修正.xlsx").write_bytes(b"not an Excel archive")
    groups = [
        ("cbanner_womens", "shoe001", 1), ("cbanner_womens", "SHOE001", 2),
        ("cbanner_womens", "SHOE002", 1), ("cbanner_womens", None, 1),
        ("eblan", "ONLY-FOREIGN", 1),
    ]
    report = audit.collect_report(tmp_path, groups)
    womens = report["brands"]["cbanner_womens"]
    assert womens["products"] == 5
    assert womens["original_skus"] == 2
    assert womens["original_skus_with_file"] == 1
    assert womens["original_skus_without_summary"] == 1
    assert womens["products_missing_original_sku"] == 1
    assert report["matched_reports"] == 2
    assert report["issues_by_type"] == {
        "missing": 1, "ambiguous": 1, "no_archive_match": 1, "missing_original_sku": 1, "missing_result": 1,
        "unavailable_workbook": 1,
    }
    assert next(issue for issue in report["issues"] if issue["status"] == "unavailable_workbook")["workbook"] == "正在修正.xlsx"
    (tmp_path / SUMMARY_DIR / "正在修正.xlsx").unlink()
    unresolved = next(issue for issue in report["issues"] if issue["status"] == "missing")
    assert unresolved["sources"] == [{
        "name": "缺少.pdf", "workbook": "千百度质检表格汇总.xlsx", "sheet": "报告", "row": 2,
    }]
    assert [report.status for report in StockQualityReports(tmp_path).for_product("shoe001", "cbanner_womens")] == [
        "matched", "number_match", "missing", "ambiguous",
    ]
    (tmp_path / "缺少.pdf").write_bytes(b"provided later")
    updated = audit.collect_report(tmp_path, groups)
    assert updated["matched_reports"] == 3 and "missing" not in updated["issues_by_type"]
    assert StockQualityReports(tmp_path).for_product("SHOE001", "cbanner_womens")[2].status == "matched"


def test_daily_audit_records_failure_retry_and_idempotence(tmp_path):
    url = os.getenv("TEST_STOCK_OVERVIEW_DATABASE_URL")
    if not url:
        pytest.skip("requires an isolated PostgreSQL database")
    repository = ProductRepository(url)
    statuses = ScheduledTaskStatusRepository(url)
    try:
        SUPPLIER_BRAND_TABLE.create(repository.engine)
        for table in PRODUCT_ARCHIVE_TABLES.values():
            table.create(repository.engine)
        archive = PRODUCT_ARCHIVE_TABLES["cbanner_womens"]
        common = {"source_workbook": "", "source_sheet": "", "source_row_number": "", "raw_payload": {}}
        with repository.engine.begin() as connection:
            connection.execute(archive.insert().values(**common, sku="CHILD01", original_sku="SHOE001"))
            connection.execute(archive.insert().values(**common, sku="CHILD02", original_sku="SHOE001"))
            connection.execute(archive.insert().values(**common, sku="ARCHIVED01", original_sku="ARCHIVED",
                                                       deleted_at=audit.datetime.now(audit.BUSINESS_TIMEZONE)))

        source, output = tmp_path / "source", tmp_path / "output"
        business_date = date(2026, 11, 27)
        def run(**kwargs):
            return audit.run_daily_check(repository, statuses, source, output, business_date, **kwargs)

        assert run() == 1
        assert not output.exists()
        assert not statuses.is_success(audit.TASK_NAME, business_date)
        (source / SUMMARY_DIR).mkdir(parents=True)
        _workbook(source, "千百度质检表格汇总.xlsx", [("SHOE001", "补交.pdf")])
        assert run() == 0
        path = output / f"check-{business_date}.json"
        old_report = path.read_bytes()
        first = json.loads(old_report)
        assert first["brands"]["cbanner_womens"]["products"] == 2
        assert first["issues_by_type"] == {"missing": 1}
        (source / "补交.pdf").write_bytes(b"provided")
        assert run() == 0 and path.read_bytes() == old_report
        assert run(force=True) == 0
        assert json.loads(path.read_bytes())["issues_by_type"] == {}
        source.rename(tmp_path / "unavailable")
        latest = path.read_bytes()
        assert run(force=True) == 1 and path.read_bytes() == latest
        status = SCHEDULED_TASK_STATUS_TABLE
        with statuses.engine.connect() as connection:
            assert connection.execute(select(status.c.status, status.c.attempts)).one() == ("failed", 4)
    finally:
        repository.engine.dispose()
        statuses.engine.dispose()

