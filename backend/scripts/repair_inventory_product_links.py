from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import bindparam, create_engine, insert, select, text, update

from config import load_settings
from domain.inventory_brands import inventory_brand_groups
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE, SUPPLIER_BRAND_TABLE
from domain.operation_log_schema import OPERATION_LOG_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE, _identifier
from scripts.check_inventory_product_links import add_candidate_information, review_statement
from storage.operation_log_repository import clean_payload


REPAIR_ISSUES = ("unlinked", "inactive_identity")


def write_json(path, data):
    path.write_text(json.dumps(clean_payload(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repair_candidate(row):
    candidates = row["candidates"]
    if row["issue_type"] not in REPAIR_ISSUES or row["candidate_count"] != 1 or len(candidates) != 1:
        return None
    candidate = candidates[0]
    if candidate["sku"] != row["product_code"]:
        return None
    if row["document_brand"] and candidate["brand"] != row["document_brand"]:
        return None
    if row["linked_brand"] and candidate["brand"] != row["linked_brand"]:
        return None
    return candidate


def preview(connection):
    groups = inventory_brand_groups(connection.execute(
        select(SUPPLIER_BRAND_TABLE.c.code, SUPPLIER_BRAND_TABLE.c.name)
    ).mappings())
    source = review_statement(groups).subquery()
    rows = [dict(row) for row in connection.execute(select(source).where(
        source.c.issue_type.in_(REPAIR_ISSUES),
    ).order_by(source.c.detail_id)).mappings()]
    add_candidate_information(connection, rows, groups)
    codes = {row["product_code"] for row in rows}
    global_candidates = defaultdict(list)
    identity = PRODUCT_ARCHIVE_IDENTITY_TABLE
    for item in connection.execute(select(
        identity.c.id, identity.c.brand, identity.c.sku,
    ).where(identity.c.is_active.is_(True), identity.c.sku.in_(codes)).order_by(identity.c.id)).mappings():
        global_candidates[item["sku"]].append(dict(item))
    repairs = []
    unresolved = []
    for row in rows:
        candidate = repair_candidate(row)
        if candidate:
            repairs.append({**row, "new_identity_id": candidate["id"]})
        else:
            alternatives = global_candidates[row["product_code"]]
            reason = (
                "仅匹配其他品牌，禁止跨品牌强绑" if alternatives and row["candidate_count"] == 0
                else "无对应有效档案，需补档或核对历史货号" if not alternatives and row["candidate_count"] == 0
                else "非唯一完整货号匹配，需人工确认"
            )
            unresolved.append({**row, "reason": reason, "other_brand_candidates": alternatives})
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "issue_counts": dict(Counter(row["issue_type"] for row in rows)),
        "repair_count": len(repairs),
        "unresolved_count": len(unresolved),
        "unresolved_reasons": dict(Counter(row["reason"] for row in unresolved)),
        "repairs": repairs,
        "unresolved": unresolved,
        "notice": "仅修复同品牌、同完整货号的唯一关联；不修改单价、金额、数量、历史货号或其他商品属性。",
    }


def write_unresolved(path, rows):
    headers = ["明细ID", "单据编号", "单据类型", "单据品牌", "货号", "商品名称", "原单价", "原金额", "未修复原因", "其他品牌候选"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                row["detail_id"], row["document_number"], row["document_type"], row["document_brand"],
                row["product_code"], row["product_name"], row["unit_price"], row["amount"], row["reason"],
                "；".join(f"{item['brand']}:{item['sku']}" for item in row["other_brand_candidates"]),
            ])


def assert_identity_only(before, after, identity_id):
    expected = {**before, "product_identity_id": identity_id}
    if {key: value for key, value in after.items() if key != "updated_at"} != {
        key: value for key, value in expected.items() if key != "updated_at"
    }:
        raise ValueError(f"Unexpected business-field change in detail {before['id']}; repair rolled back")


def apply_repairs(connection, repairs, output_directory):
    if not repairs:
        return {"repaired": 0, "log_ids": []}
    document_ids = sorted({row["document_id"] for row in repairs})
    detail_ids = sorted(row["detail_id"] for row in repairs)
    identity_ids = sorted({row["new_identity_id"] for row in repairs})
    records = [dict(row) for row in connection.execute(select(INVENTORY_TABLE).where(
        INVENTORY_TABLE.c.id.in_(document_ids),
    ).order_by(INVENTORY_TABLE.c.id).with_for_update()).mappings()]
    details = [dict(row) for row in connection.execute(select(INVENTORY_DETAIL_TABLE).where(
        INVENTORY_DETAIL_TABLE.c.document_id.in_(document_ids),
    ).order_by(INVENTORY_DETAIL_TABLE.c.id).with_for_update()).mappings()]
    identities = {row["id"]: dict(row) for row in connection.execute(select(PRODUCT_ARCHIVE_IDENTITY_TABLE).where(
        PRODUCT_ARCHIVE_IDENTITY_TABLE.c.id.in_(identity_ids),
    ).order_by(PRODUCT_ARCHIVE_IDENTITY_TABLE.c.id).with_for_update(read=True)).mappings()}
    planned = {row["detail_id"]: row for row in repairs}
    before = {row["id"]: row for row in details}
    record_by_id = {row["id"]: row for row in records}
    for detail_id in detail_ids:
        item = planned[detail_id]
        detail = before[detail_id]
        record = record_by_id[item["document_id"]]
        identity = identities[item["new_identity_id"]]
        if (record["deleted_at"] is not None or record["document_type"] != item["document_type"]
            or detail["product_identity_id"] != item["product_identity_id"]
            or detail["product_code"] != item["product_code"]
            or detail["unit_price"] != item["unit_price"] or detail["amount"] != item["amount"]
            or detail["quantity"] != item["quantity"]
            or not identity["is_active"] or identity["sku"] != item["product_code"]
            or identity["brand"] != item["candidate_brand"]):
            raise ValueError(f"Detail {detail_id} changed after preview; refusing to repair")
    by_table = defaultdict(list)
    for identity in identities.values():
        by_table[_identifier(identity["source_table"])].append(identity)
    for table, items in by_table.items():
        archive_rows = {row["id"]: row for row in connection.execute(text(
            f"SELECT id, sku, deleted_at FROM {table} WHERE id IN :ids ORDER BY id FOR SHARE"
        ).bindparams(bindparam("ids", expanding=True)), {"ids": [row["source_product_id"] for row in items]}).mappings()}
        for identity in items:
            archive = archive_rows.get(identity["source_product_id"])
            if archive is None or archive["deleted_at"] is not None or archive["sku"] != identity["sku"]:
                raise ValueError("Target identity does not point to an existing active product archive")
    write_json(output_directory / "before.json", {"records": records, "details": details, "identities": list(identities.values())})
    results = []
    logs = []
    for detail_id in detail_ids:
        item = planned[detail_id]
        after = dict(connection.execute(update(INVENTORY_DETAIL_TABLE).where(
            INVENTORY_DETAIL_TABLE.c.id == detail_id,
            INVENTORY_DETAIL_TABLE.c.document_id == item["document_id"],
        ).values(product_identity_id=item["new_identity_id"]).returning(INVENTORY_DETAIL_TABLE)).mappings().one())
        assert_identity_only(before[detail_id], after, item["new_identity_id"])
        results.append(after)
        logs.append({
            "module": "purchase" if item["document_type"] == "进货订单" else "inventory",
            "action": "detail_update", "entity_type": "inventory_detail", "entity_id": str(detail_id),
            "entity_label": item["product_code"],
            "summary": f"修复 {item['document_number']} 明细 {item['product_code']} 的商品档案关联（用户授权）；原货号、数量、单价和金额均保留",
            "changed_fields": [{"field": "product_identity_id", "label": "商品档案关联", "before": item["product_identity_id"], "after": item["new_identity_id"]}],
            "before_data": clean_payload(before[detail_id]), "after_data": clean_payload(after),
            "display_name": "数据修正（用户授权）",
        })
    log_ids = list(connection.execute(insert(OPERATION_LOG_TABLE).returning(OPERATION_LOG_TABLE.c.id), logs).scalars())
    after_details = [dict(row) for row in connection.execute(select(INVENTORY_DETAIL_TABLE).where(
        INVENTORY_DETAIL_TABLE.c.document_id.in_(document_ids),
    ).order_by(INVENTORY_DETAIL_TABLE.c.id)).mappings()]
    for after in after_details:
        if after["id"] in planned:
            assert_identity_only(before[after["id"]], after, planned[after["id"]]["new_identity_id"])
        elif after != before[after["id"]]:
            raise ValueError("Unrelated document details changed")
    after_records = [dict(row) for row in connection.execute(select(INVENTORY_TABLE).where(
        INVENTORY_TABLE.c.id.in_(document_ids),
    ).order_by(INVENTORY_TABLE.c.id)).mappings()]
    if after_records != records:
        raise ValueError("Document headers or totals unexpectedly changed")
    write_json(output_directory / "after.json", {"records": after_records, "repaired_details": results, "log_ids": log_ids})
    return {"repaired": len(results), "documents": len(records), "log_ids": log_ids, "business_fields_unchanged": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="修复唯一同品牌同货号关联，默认只预览")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "result.json"
    if result_path.exists() and json.loads(result_path.read_text(encoding="utf-8")).get("data_committed"):
        raise ValueError("This repair directory already contains a committed repair")
    engine = create_engine(load_settings(require_database=True).database_url, connect_args={
        "connect_timeout": 10, "application_name": "authorized_inventory_link_repair",
    })
    result = {"status": "preview", "data_committed": False}
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '90s'"))
            plan = preview(connection)
        preview_path = args.output_dir / "preview.json"
        if args.execute:
            if not preview_path.exists():
                raise ValueError("Run the preview first")
            approved = json.loads(preview_path.read_text(encoding="utf-8"))
            if clean_payload(plan["repairs"]) != approved["repairs"] or plan["issue_counts"] != approved["issue_counts"]:
                raise ValueError("Repair plan changed since preview; inspect a fresh preview")
        else:
            write_json(preview_path, plan)
        write_unresolved(args.output_dir / "unresolved.csv", plan["unresolved"])
        result.update({key: value for key, value in plan.items() if key not in {"repairs", "unresolved"}})
        if args.execute:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL statement_timeout = '90s'"))
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('authorized_inventory_link_repair'))"))
                result["repair"] = apply_repairs(connection, plan["repairs"], args.output_dir)
            result.update(status="completed", data_committed=True, completed_at=datetime.now().astimezone().isoformat())
        write_json(result_path, result)
        print(json.dumps(clean_payload(result), ensure_ascii=False))
        print(f"[OUTPUT] {result_path}")
        return 0
    except Exception as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
        write_json(result_path, result)
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
