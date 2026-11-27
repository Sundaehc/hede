"""Audit the quality report share against active product archives."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import text

from config import BACKEND_ROOT, load_settings
from storage.product_repository import ProductRepository
from storage.stock_quality_reports import _sku, build_catalog, match_product_reports
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "check_stock_quality_reports_daily"
TASK_LOCK = 2026112701
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))
OUTPUT_DIRECTORY = BACKEND_ROOT / "logs" / "stock_quality_reports"


def collect_report(root, archive_groups):
    issues = []
    catalog = build_catalog(root, incomplete_rows=issues, unavailable_workbooks=issues)
    archive = Counter()
    by_brand = defaultdict(Counter)
    for brand, raw_original, count in archive_groups:
        original = _sku(raw_original)
        by_brand[brand]["products"] += count
        if original:
            archive[brand, original] += count
        else:
            by_brand[brand]["products_missing_original_sku"] += count

    linked_references = set()
    for brand, original in sorted(archive):
        counts = by_brand[brand]
        counts["original_skus"] += 1
        if original not in catalog.references:
            continue
        reports = match_product_reports(catalog, original, brand)
        if not reports:
            continue
        counts["original_skus_with_summary"] += 1
        counts["original_skus_with_file"] += int(any(report.path is not None for report in reports))
        for report in reports:
            linked_references.update(report.sources)
            counts[report.status] += 1
            if report.path is None:
                issues.append({
                    "status": report.status, "brand": brand, "original_sku": original,
                    "report": report.name, "sources": [asdict(source) for source in report.sources],
                })

    originals_by_reference = defaultdict(set)
    for original, references in catalog.references.items():
        for reference in references:
            if reference not in linked_references:
                originals_by_reference[reference].add(original)
    for source, originals in sorted(originals_by_reference.items(),
                                   key=lambda item: (item[0].workbook, item[0].sheet, item[0].row, item[0].name)):
        issues.append({"status": "no_archive_match", "original_skus": sorted(originals), **asdict(source)})

    for counts in by_brand.values():
        counts["original_skus_without_summary"] = counts["original_skus"] - counts["original_skus_with_summary"]
    return {
        "brands": {brand: dict(by_brand[brand]) for brand in sorted(by_brand)},
        "matched_reports": sum(counts["matched"] + counts["number_match"] for counts in by_brand.values()),
        "issues_by_type": dict(Counter(issue["status"] for issue in issues)),
        "issues": issues,
    }


def save_report(report, output_directory, business_date):
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"check-{business_date}.json"
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_directory, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            json.dump(report, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.close()
            temporary_path.replace(path)
        finally:
            temporary.close()
            temporary_path.unlink(missing_ok=True)
    return path


def run_daily_check(repository, statuses, root, output_directory, business_date: date, *, force=False):
    with statuses.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        lock_params = {"key": TASK_LOCK}
        if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), lock_params).scalar_one():
            print("[WAIT] 质检报告巡检正在执行")
            return 1
        try:
            if not force and statuses.is_success(TASK_NAME, business_date):
                print(f"[SKIP] {business_date} 质检报告已巡检")
                return 0

            statuses.mark_running(TASK_NAME, business_date, source_path=root)
            try:
                report = collect_report(root, repository.iter_quality_archive_groups())
                report["business_date"] = business_date.isoformat()
                report["checked_at"] = datetime.now(BUSINESS_TIMEZONE).isoformat(timespec="seconds")
                path = save_report(report, output_directory, business_date)
                issues = report["issues_by_type"]
                message = (
                    f"质检报告巡检完成：匹配 {report['matched_reports']} 条报告关联，"
                    f"缺原件 {issues.get('missing', 0)} 项，冲突 {issues.get('ambiguous', 0)} 项，"
                    f"未关联商品档案 {issues.get('no_archive_match', 0)} 项，"
                    f"汇总缺字段 {issues.get('missing_original_sku', 0) + issues.get('missing_result', 0)} 项，"
                    f"汇总表未读取 {issues.get('unavailable_workbook', 0)} 份"
                )
                statuses.mark_finished(
                    TASK_NAME, business_date, status="success", message=message, source_path=root,
                    result={key: value for key, value in report.items() if key != "issues"} | {"report": str(path)},
                )
                print(f"[OK] {message}\n[OUTPUT] {path}")
                return 0
            except Exception as error:
                message = f"质检报告巡检失败：{type(error).__name__}: {error}"[:2000]
                statuses.mark_finished(TASK_NAME, business_date, status="failed", message=message, source_path=root)
                print(f"[FAILED] {message}")
                return 1
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), lock_params)


def check_quality_reports(settings, statuses, business_date: date, *, output_directory=OUTPUT_DIRECTORY, force=False):
    repository = ProductRepository(settings.database_url)
    try:
        return run_daily_check(
            repository, statuses, settings.stock_quality_report_root, output_directory, business_date, force=force,
        )
    finally:
        repository.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="每日只读巡检商品档案质检报告并输出待核对清单")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIRECTORY)
    parser.add_argument("--force", action="store_true", help="当天已成功时也重新巡检")
    args = parser.parse_args()

    settings = load_settings(require_database=True)
    statuses = ScheduledTaskStatusRepository(settings.database_url)
    try:
        return check_quality_reports(
            settings, statuses, datetime.now(BUSINESS_TIMEZONE).date(),
            output_directory=args.output_dir, force=args.force,
        )
    finally:
        statuses.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

