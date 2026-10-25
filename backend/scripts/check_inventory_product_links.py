from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import and_, case, create_engine, func, or_, select, text

from config import load_settings
from domain.inventory_brands import inventory_brand_groups, inventory_brand_key
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, SUPPLIER_BRAND_TABLE, SUPPLIER_TABLE
from domain.inventory_sources import ACCOUNTING_DOCUMENT_TYPES
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE


ISSUE_LABELS = {
    "unlinked": "未关联商品档案",
    "missing_identity": "关联记录不存在",
    "inactive_identity": "关联档案已失效",
    "brand_mismatch": "关联品牌不一致",
    "purchase_code_mismatch": "采购单货号与关联档案不一致",
}
DEFAULT_OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "logs" / "inventory-product-links"


def review_statement(brand_groups):
    detail = INVENTORY_DETAIL_TABLE
    record = INVENTORY_TABLE
    identity = PRODUCT_ARCHIVE_IDENTITY_TABLE
    aliases = {alias.casefold(): code for code, values in brand_groups.items() for alias in values}
    raw_brand = func.lower(func.trim(func.coalesce(record.c.raw_payload["brand"].as_string(), "")))
    document_brand = case(aliases, value=raw_brand, else_=raw_brand) if aliases else raw_brand
    product_code = func.trim(detail.c.product_code)
    current_code = func.coalesce(func.nullif(func.trim(identity.c.sku), ""), func.trim(identity.c.original_sku), "")
    issue_type = case(
        (detail.c.product_identity_id.is_(None), "unlinked"),
        (identity.c.id.is_(None), "missing_identity"),
        (identity.c.is_active.is_not(True), "inactive_identity"),
        (and_(document_brand != "", document_brand != identity.c.brand), "brand_mismatch"),
        (and_(record.c.document_type == "进货订单", product_code != current_code), "purchase_code_mismatch"),
        else_="",
    )
    return select(
        detail.c.id.label("detail_id"), detail.c.document_id, record.c.document_number,
        record.c.document_type, record.c.supplier, document_brand.label("document_brand"),
        detail.c.product_code, detail.c.product_name, detail.c.quantity, detail.c.unit_price,
        detail.c.amount, detail.c.product_identity_id, identity.c.brand.label("linked_brand"),
        identity.c.sku.label("linked_sku"), identity.c.original_sku.label("linked_original_sku"),
        identity.c.is_active.label("identity_active"), issue_type.label("issue_type"),
    ).select_from(
        detail.join(record, detail.c.document_id == record.c.id)
        .outerjoin(identity, detail.c.product_identity_id == identity.c.id)
    ).where(
        record.c.deleted_at.is_(None),
        or_(record.c.document_type.is_(None), record.c.document_type.not_in(ACCOUNTING_DOCUMENT_TYPES)),
        func.nullif(product_code, "").is_not(None),
    )


def add_candidate_information(connection, samples, brand_groups):
    if not samples:
        return
    supplier_brands = defaultdict(set)
    supplier_names = {str(row["supplier"] or "").strip().casefold() for row in samples}
    for row in connection.execute(select(SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.brand).where(
        func.lower(func.trim(SUPPLIER_TABLE.c.name)).in_(supplier_names),
    )).mappings():
        brand = inventory_brand_key(row["brand"], brand_groups)
        if brand:
            supplier_brands[str(row["name"]).strip().casefold()].add(brand)
    codes = {str(row["product_code"]).strip() for row in samples}
    identity = PRODUCT_ARCHIVE_IDENTITY_TABLE
    exact = defaultdict(list)
    original = defaultdict(list)
    for row in connection.execute(select(
        identity.c.id, identity.c.brand, identity.c.sku, identity.c.original_sku,
    ).where(
        identity.c.is_active.is_(True),
        or_(identity.c.sku.in_(codes), identity.c.original_sku.in_(codes)),
    ).order_by(identity.c.id)).mappings():
        exact[(row["brand"], row["sku"])].append(dict(row))
        original[(row["brand"], row["original_sku"])].append(dict(row))
    for sample in samples:
        brand = sample["document_brand"]
        supplier_values = supplier_brands[str(sample["supplier"] or "").strip().casefold()]
        if not brand and sample["document_type"] in {"进货订单", "进货单", "进货退货单"}:
            if len(supplier_values) == 1:
                brand = next(iter(supplier_values))
        brand = brand or sample["linked_brand"]
        code = str(sample["product_code"]).strip()
        candidates = (exact.get((brand, code)) or original.get((brand, code)) or []) if brand else []
        sample["candidate_brand"] = brand or ""
        sample["candidate_count"] = len(candidates)
        sample["candidates"] = candidates[:10]
        sample["candidate_status"] = (
            "品牌不明确，需人工确认" if not brand
            else "唯一候选，仅供人工确认" if len(candidates) == 1
            else "存在多个候选，禁止自动关联" if candidates
            else "未找到同品牌有效档案"
        )


def collect_report(connection, *, sample_limit=100):
    if sample_limit < 1:
        raise ValueError("sample_limit must be positive")
    brands = [dict(row) for row in connection.execute(
        select(SUPPLIER_BRAND_TABLE.c.code, SUPPLIER_BRAND_TABLE.c.name)
    ).mappings()]
    groups = inventory_brand_groups(brands)
    source = review_statement(groups).subquery()
    counts = list(connection.execute(select(
        source.c.issue_type, source.c.document_type, func.count().label("details"),
    ).group_by(source.c.issue_type, source.c.document_type)).mappings())
    issue_counts = Counter()
    document_counts = Counter()
    checked = 0
    for row in counts:
        checked += row["details"]
        if row["issue_type"]:
            issue_counts[row["issue_type"]] += row["details"]
            document_counts[row["document_type"] or "未填写单据类型"] += row["details"]
    samples = []
    for issue_type in ISSUE_LABELS:
        if issue_counts[issue_type]:
            samples.extend(dict(row) for row in connection.execute(
                select(source).where(source.c.issue_type == issue_type)
                .order_by(source.c.detail_id).limit(sample_limit)
            ).mappings())
    for sample in samples:
        sample["issue_label"] = ISSUE_LABELS[sample["issue_type"]]
    add_candidate_information(connection, samples, groups)
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "read_only",
        "checked_product_details": checked,
        "issue_count": sum(issue_counts.values()),
        "counts_by_issue": {ISSUE_LABELS[key]: value for key, value in issue_counts.items()},
        "counts_by_document_type": dict(document_counts),
        "samples": samples,
        "sample_limit_per_issue": sample_limit,
        "samples_truncated": sum(issue_counts.values()) > len(samples),
        "notice": "仅检查关联，不自动重绑、不修改单价、数量、金额或历史货号；候选档案须人工确认。",
    }


def check_links(engine, *, sample_limit=100):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '180s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            return collect_report(connection, sample_limit=sample_limit)


def save_report(report, output_directory):
    output_directory.mkdir(parents=True, exist_ok=True)
    filename = "check-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
    report_path = output_directory / filename
    data = json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
    report_path.write_text(data, encoding="utf-8")
    temporary = output_directory / (filename + ".latest.tmp")
    temporary.write_text(data, encoding="utf-8")
    temporary.replace(output_directory / "latest.json")
    return report_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读检查采购单、经营历程与商品档案的关联")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--sample-limit", type=int, default=100, help="每类异常最多保留的明细示例数")
    args = parser.parse_args(argv)
    if args.sample_limit < 1:
        parser.error("每类异常示例数必须大于零")
    engine = create_engine(load_settings(require_database=True).database_url, connect_args={
        "connect_timeout": 10,
        "application_name": "check_inventory_product_links",
    })
    try:
        report = check_links(engine, sample_limit=args.sample_limit)
        report_path = save_report(report, args.output_dir)
        print(f"[OUTPUT] 关联检查报告：{report_path}")
        print(f"[INFO] {report['notice']}")
        if report["issue_count"]:
            counts = "；".join(f"{label} {count} 条" for label, count in report["counts_by_issue"].items())
            print(f"[FAILED] 商品关联检查完成，发现 {report['issue_count']} 条需人工确认的异常：{counts}。报告：{report_path}")
            return 1
        print(f"[OK] 商品关联检查完成，共检查 {report['checked_product_details']} 条明细，未发现异常。")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
