from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

from sqlalchemy import create_engine, insert, select, text, update

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from api.operation_log_utils import DETAIL_FIELD_LABELS, INVENTORY_FIELD_LABELS, build_changed_fields
from config import load_settings
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from domain.operation_log_schema import OPERATION_LOG_TABLE
from domain.product_archive_identity_schema import PRODUCT_ARCHIVE_IDENTITY_TABLE
from storage.inventory_repository import InventoryRepository
from storage.operation_log_repository import clean_payload


PRODUCT_CODE = "NAG2658015B01"
IDENTITY_ID = 11136086
NEW_PRICE = Decimal("250.60")
OLD_PRICE = Decimal("268.00")
EXPECTED = {
    310861: {"document_id": 12170, "document_number": "JHD-2026-10-09-0001", "document_type": "进货单",
             "quantity": Decimal("60"), "old_total": Decimal("16414.80"), "new_total": Decimal("15370.80")},
    3185141: {"document_id": 110422, "document_number": "JHD-2026-09-27-0001", "document_type": "进货单",
              "quantity": Decimal("1"), "old_total": Decimal("602.80"), "new_total": Decimal("585.40")},
    3358869: {"document_id": 112582, "document_number": "JHTHD-2026-10-23-0001", "document_type": "进货退货单",
              "quantity": Decimal("2"), "old_total": Decimal("-1375.00"), "new_total": Decimal("-1340.20")},
}
DOCUMENT_IDS = sorted({1770, 110423, *(item["document_id"] for item in EXPECTED.values())})
OUTPUT_DIRECTORY = Path(__file__).resolve().parent
RESULT_PATH = OUTPUT_DIRECTORY / "result.json"


def save_json(filename, payload):
    (OUTPUT_DIRECTORY / filename).write_text(
        json.dumps(clean_payload(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )


def snapshot(connection, *, lock=False):
    records_statement = select(INVENTORY_TABLE).where(
        INVENTORY_TABLE.c.id.in_(DOCUMENT_IDS),
    ).order_by(INVENTORY_TABLE.c.id)
    details_statement = select(INVENTORY_DETAIL_TABLE).where(
        INVENTORY_DETAIL_TABLE.c.document_id.in_(DOCUMENT_IDS),
    ).order_by(INVENTORY_DETAIL_TABLE.c.id)
    identity_statement = select(PRODUCT_ARCHIVE_IDENTITY_TABLE).where(
        PRODUCT_ARCHIVE_IDENTITY_TABLE.c.id == IDENTITY_ID,
    )
    if lock:
        records_statement = records_statement.with_for_update()
        details_statement = details_statement.with_for_update()
        identity_statement = identity_statement.with_for_update(read=True)
    records = [dict(row) for row in connection.execute(records_statement).mappings()]
    details = [dict(row) for row in connection.execute(details_statement).mappings()]
    identity = dict(connection.execute(identity_statement).mappings().one())
    archive = dict(connection.execute(text(
        "SELECT id, sku, cost, deleted_at FROM manual_product_archive_31 WHERE id = 61"
        + (" FOR SHARE" if lock else "")
    )).mappings().one())
    related_ids = list(connection.execute(select(INVENTORY_DETAIL_TABLE.c.id).where(
        INVENTORY_DETAIL_TABLE.c.product_code == PRODUCT_CODE,
    ).order_by(INVENTORY_DETAIL_TABLE.c.id)).scalars())
    return {"records": records, "details": details, "identity": identity,
            "archive": archive, "related_detail_ids": related_ids}


def totals(record, details):
    quantity = sum((row["quantity"] or Decimal("0")) for row in details)
    amount = sum((row["amount"] or Decimal("0")) for row in details)
    return (
        InventoryRepository._apply_document_total_sign(record["document_type"], quantity),
        InventoryRepository._apply_document_total_sign(record["document_type"], amount),
    )


def plan_repair(before):
    identity = before["identity"]
    archive = before["archive"]
    if (not identity["is_active"] or identity["brand"] != "ns"
        or identity["source_table"] != "manual_product_archive_31"
        or identity["source_product_id"] != 61 or identity["sku"] != PRODUCT_CODE
        or archive["sku"] != PRODUCT_CODE or archive["cost"] != NEW_PRICE
        or archive["deleted_at"] is not None):
        raise ValueError("Current archive no longer matches the verified cost")
    if before["related_detail_ids"] != sorted([36819, 310861, 3185141, 3185144, 3358869]):
        raise ValueError("Related product details changed after inspection")
    records = {row["id"]: row for row in before["records"]}
    details = {row["id"]: row for row in before["details"]}
    plan = []
    for detail_id, expected in EXPECTED.items():
        record = records[expected["document_id"]]
        detail = details[detail_id]
        if (record["document_number"] != expected["document_number"]
            or record["document_type"] != expected["document_type"]
            or record["deleted_at"] is not None or record["raw_payload"].get("brand") != "ns"
            or record["amount"] != expected["old_total"]
            or detail["document_id"] != record["id"]
            or detail["product_code"] != PRODUCT_CODE or detail["product_identity_id"] != IDENTITY_ID
            or detail["unit_price"] != OLD_PRICE or detail["quantity"] != expected["quantity"]
            or detail["amount"] != OLD_PRICE * detail["quantity"]):
            raise ValueError(f"Detail {detail_id} or its document changed after inspection")
        document_details = [row for row in details.values() if row["document_id"] == record["id"]]
        if totals(record, document_details) != (record["total_count"], record["amount"]):
            raise ValueError("Existing document totals are inconsistent")
        plan.append({"detail_id": detail_id, **expected, "old_price": OLD_PRICE, "new_price": NEW_PRICE,
                     "old_detail_amount": detail["amount"], "new_detail_amount": NEW_PRICE * detail["quantity"]})
    return plan


def assert_preserved(before, after):
    if any(before[key] != after[key] for key in ("archive", "identity", "related_detail_ids")):
        raise ValueError("Archive, identity or related detail membership unexpectedly changed")
    if len(before["details"]) != len(after["details"]) or len(before["records"]) != len(after["records"]):
        raise ValueError("Document or detail membership unexpectedly changed")
    after_details = {row["id"]: row for row in after["details"]}
    for detail in before["details"]:
        expected = dict(detail)
        allowed_fields = set()
        if detail["id"] in EXPECTED:
            expected.update(unit_price=NEW_PRICE, amount=NEW_PRICE * detail["quantity"])
            allowed_fields.add("updated_at")
        actual = after_details[detail["id"]]
        if {key: value for key, value in actual.items() if key not in allowed_fields} != {
            key: value for key, value in expected.items() if key not in allowed_fields
        }:
            raise ValueError(f"Unexpected detail field change: {detail['id']}")
    changed_records = {item["document_id"]: item for item in EXPECTED.values()}
    after_records = {row["id"]: row for row in after["records"]}
    for record in before["records"]:
        expected = dict(record)
        allowed_fields = set()
        if record["id"] in changed_records:
            expected["amount"] = changed_records[record["id"]]["new_total"]
            allowed_fields.add("updated_at")
        actual = after_records[record["id"]]
        if {key: value for key, value in actual.items() if key not in allowed_fields} != {
            key: value for key, value in expected.items() if key not in allowed_fields
        }:
            raise ValueError(f"Unexpected document field change: {record['id']}")
        if record["id"] in changed_records:
            document_details = [row for row in after["details"] if row["document_id"] == record["id"]]
            if totals(actual, document_details) != (actual["total_count"], actual["amount"]):
                raise ValueError("Updated document totals are inconsistent")


def write_log(connection, *, before, after, detail=False):
    labels = DETAIL_FIELD_LABELS if detail else INVENTORY_FIELD_LABELS
    changes = build_changed_fields(before, after, labels)
    return connection.execute(insert(OPERATION_LOG_TABLE).values(
        module="inventory", action="detail_update" if detail else "update",
        entity_type="inventory_detail" if detail else "inventory_record", entity_id=str(after["id"]),
        entity_label=PRODUCT_CODE if detail else after["document_number"],
        summary=(f"修正经营历程货号 {PRODUCT_CODE} 成本：268 → 250.60，并重算金额（用户授权）"
                 if detail else f"修正 {after['document_number']} 商品成本后重算整单金额（用户授权）"),
        changed_fields=clean_payload(changes), before_data=clean_payload(before), after_data=clean_payload(after),
        display_name="数据修正（用户授权）",
    ).returning(OPERATION_LOG_TABLE.c.id)).scalar_one()


def main():
    parser = argparse.ArgumentParser(description="修正已确认的三条经营历程成本，保留销售价和其他业务字段")
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    if RESULT_PATH.exists() and json.loads(RESULT_PATH.read_text(encoding="utf-8")).get("data_committed"):
        raise RuntimeError("This repair has already committed; refusing to execute again")
    if arguments.execute and not (OUTPUT_DIRECTORY / "preview.json").exists():
        raise RuntimeError("Run the read-only preview before executing")
    engine = create_engine(load_settings(require_database=True).database_url, connect_args={
        "connect_timeout": 10, "application_name": "authorized_nag_inventory_cost_repair",
    })
    try:
        with engine.begin() as connection:
            if not arguments.execute:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            before = snapshot(connection, lock=arguments.execute)
            plan = plan_repair(before)
            if not arguments.execute:
                save_json("preview.json", {"generated_at": datetime.now().astimezone(), "plan": plan, "before": before})
                print(json.dumps(clean_payload({"mode": "preview", "plan": plan}), ensure_ascii=True))
                return
            preview = json.loads((OUTPUT_DIRECTORY / "preview.json").read_text(encoding="utf-8"))
            if preview["before"] != clean_payload(before):
                raise ValueError("Data changed since preview; refusing to execute")
            save_json("before.json", before)
            for item in plan:
                connection.execute(update(INVENTORY_DETAIL_TABLE).where(
                    INVENTORY_DETAIL_TABLE.c.id == item["detail_id"],
                    INVENTORY_DETAIL_TABLE.c.document_id == item["document_id"],
                ).values(unit_price=NEW_PRICE, amount=item["new_detail_amount"]))
                connection.execute(update(INVENTORY_TABLE).where(
                    INVENTORY_TABLE.c.id == item["document_id"],
                ).values(amount=item["new_total"]))
            after = snapshot(connection)
            assert_preserved(before, after)
            after_details = {row["id"]: row for row in after["details"]}
            after_records = {row["id"]: row for row in after["records"]}
            log_ids = [write_log(connection, before=row, after=after_details[row["id"]], detail=True)
                       for row in before["details"] if row["id"] in EXPECTED]
            document_ids = {item["document_id"] for item in plan}
            log_ids.extend(write_log(connection, before=row, after=after_records[row["id"]])
                           for row in before["records"] if row["id"] in document_ids)
            save_json("after.json", after)
        result = {"status": "committed", "data_committed": True, "committed_at": datetime.now().astimezone(),
                  "updated_details": len(plan), "updated_documents": len(plan), "plan": plan, "operation_log_ids": log_ids}
        save_json("result.json", result)
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '20s'"))
            final = snapshot(connection)
            assert_preserved(before, final)
            if final != after:
                raise ValueError("Data changed between commit and independent verification")
            logs = list(connection.execute(select(OPERATION_LOG_TABLE.c.id).where(
                OPERATION_LOG_TABLE.c.id.in_(log_ids),
            )).scalars())
            if len(logs) != 6:
                raise ValueError("Expected six operation log records")
        verification = {"verified_at": datetime.now().astimezone(), "updated_details": 3, "updated_documents": 3,
                        "price": NEW_PRICE, "quantity_sizes_and_other_fields_unchanged": True,
                        "purchase_order_and_sales_unchanged": True, "archive_unchanged": True, "operation_logs": len(logs)}
        save_json("verification.json", verification)
        result.update(status="completed", verification=verification)
        save_json("result.json", result)
        print(json.dumps(clean_payload(result), ensure_ascii=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
