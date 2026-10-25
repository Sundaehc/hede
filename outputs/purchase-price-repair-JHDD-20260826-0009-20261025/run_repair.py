from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select, text, update

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from api.operation_log_utils import DETAIL_FIELD_LABELS, INVENTORY_FIELD_LABELS, build_changed_fields
from config import load_settings
from domain.inventory_schema import INVENTORY_DETAIL_TABLE, INVENTORY_TABLE
from domain.operation_log_schema import OPERATION_LOG_TABLE
from storage.operation_log_repository import clean_payload


DOCUMENT_ID = 1770
DETAIL_ID = 36819
DOCUMENT_NUMBER = "JHDD-2026-08-26-0009"
PRODUCT_CODE = "NAG2658015B01"
OLD_IDENTITY_ID = 63049
NEW_IDENTITY_ID = 11136086
REPORT_PATH = Path(__file__).with_name("report.json")


def save_report(report):
    REPORT_PATH.write_text(json.dumps(clean_payload(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_related_details(connection):
    return [dict(row) for row in connection.execute(
        select(INVENTORY_DETAIL_TABLE)
        .where(INVENTORY_DETAIL_TABLE.c.product_code == PRODUCT_CODE)
        .where(INVENTORY_DETAIL_TABLE.c.id != DETAIL_ID)
        .order_by(INVENTORY_DETAIL_TABLE.c.id)
    ).mappings()]


def log_change(connection, *, entity_type, before, after, summary, labels):
    changes = build_changed_fields(before, after, labels)
    return connection.execute(insert(OPERATION_LOG_TABLE).values(
        module="purchase",
        action="detail_update" if entity_type == "inventory_detail" else "update",
        entity_type=entity_type,
        entity_id=str(after["id"]),
        entity_label=PRODUCT_CODE if entity_type == "inventory_detail" else DOCUMENT_NUMBER,
        summary=summary,
        changed_fields=clean_payload(changes),
        before_data=clean_payload(before),
        after_data=clean_payload(after),
        display_name="数据修正（用户授权）",
    ).returning(OPERATION_LOG_TABLE.c.id)).scalar_one()


def main():
    engine = create_engine(
        load_settings(require_database=True).database_url,
        connect_args={"connect_timeout": 10, "application_name": "authorized_purchase_price_repair_1770"},
    )
    report = {
        "status": "validating",
        "started_at": datetime.now().astimezone().isoformat(),
        "document_number": DOCUMENT_NUMBER,
        "product_code": PRODUCT_CODE,
        "data_committed": False,
    }
    try:
        if REPORT_PATH.exists():
            previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            if previous.get("data_committed"):
                raise RuntimeError("This repair has already committed; refusing to repeat it")
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '20s'"))
            record_before = dict(connection.execute(
                select(INVENTORY_TABLE).where(INVENTORY_TABLE.c.id == DOCUMENT_ID).with_for_update()
            ).mappings().one())
            order_before = [dict(row) for row in connection.execute(
                select(INVENTORY_DETAIL_TABLE)
                .where(INVENTORY_DETAIL_TABLE.c.document_id == DOCUMENT_ID)
                .order_by(INVENTORY_DETAIL_TABLE.c.id).with_for_update()
            ).mappings()]
            detail_before = next(row for row in order_before if row["id"] == DETAIL_ID)
            archive = dict(connection.execute(text("""
                SELECT id, sku, cost, deleted_at FROM manual_product_archive_31 WHERE id = 61 FOR SHARE
            """)).mappings().one())
            identity = dict(connection.execute(text("""
                SELECT * FROM product_archive_identities WHERE id = :identity_id FOR SHARE
            """), {"identity_id": NEW_IDENTITY_ID}).mappings().one())
            if (record_before["document_number"] != DOCUMENT_NUMBER
                or record_before["document_type"] != "进货订单"
                or record_before["deleted_at"] is not None
                or record_before["amount"] != Decimal("35160")):
                raise ValueError("Purchase order changed since preview")
            if (detail_before["product_code"] != PRODUCT_CODE
                or detail_before["product_identity_id"] != OLD_IDENTITY_ID
                or detail_before["unit_price"] != Decimal("268")
                or detail_before["quantity"] != Decimal("60")
                or detail_before["amount"] != Decimal("16080")):
                raise ValueError("Purchase detail changed since preview")
            if (archive["sku"] != PRODUCT_CODE or archive["cost"] != Decimal("250.60")
                or archive["deleted_at"] is not None or not identity["is_active"]
                or identity["brand"] != "ns" or identity["source_table"] != "manual_product_archive_31"
                or identity["source_product_id"] != archive["id"] or identity["sku"] != PRODUCT_CODE):
                raise ValueError("Current product archive no longer matches the approved repair")
            related_before = read_related_details(connection)
            report.update({"record_before": record_before, "order_details_before": order_before,
                           "archive": archive, "identity": identity, "other_product_details_before": related_before})
            save_report(report)
            if "--execute" not in sys.argv:
                print(json.dumps({"document_number": DOCUMENT_NUMBER, "old_price": "268", "new_price": "250.60",
                                  "old_detail_amount": "16080", "new_detail_amount": "15036",
                                  "old_order_amount": "35160", "new_order_amount": "34116"}))
                return 0
            new_amount = (detail_before["quantity"] * archive["cost"]).quantize(Decimal("0.01"))
            detail_after = dict(connection.execute(
                update(INVENTORY_DETAIL_TABLE).where(INVENTORY_DETAIL_TABLE.c.id == DETAIL_ID)
                .where(INVENTORY_DETAIL_TABLE.c.document_id == DOCUMENT_ID)
                .values(product_identity_id=NEW_IDENTITY_ID, unit_price=archive["cost"], amount=new_amount)
                .returning(INVENTORY_DETAIL_TABLE)
            ).mappings().one())
            total_count, total_amount = connection.execute(select(
                func.coalesce(func.sum(INVENTORY_DETAIL_TABLE.c.quantity), 0),
                func.coalesce(func.sum(INVENTORY_DETAIL_TABLE.c.amount), 0),
            ).where(INVENTORY_DETAIL_TABLE.c.document_id == DOCUMENT_ID)).one()
            if total_count != Decimal("180") or total_amount != Decimal("34116"):
                raise ValueError("Recalculated order totals differ from the approved amounts")
            record_after = dict(connection.execute(
                update(INVENTORY_TABLE).where(INVENTORY_TABLE.c.id == DOCUMENT_ID)
                .values(total_count=total_count, amount=total_amount).returning(INVENTORY_TABLE)
            ).mappings().one())
            expected_detail = {**detail_before, "product_identity_id": NEW_IDENTITY_ID,
                               "unit_price": Decimal("250.60"), "amount": Decimal("15036")}
            if {key: value for key, value in detail_after.items() if key != "updated_at"} != {
                key: value for key, value in expected_detail.items() if key != "updated_at"
            }:
                raise ValueError("The detail update unexpectedly changed other fields")
            other_order_details = [row for row in order_before if row["id"] != DETAIL_ID]
            unchanged_order_details = [dict(row) for row in connection.execute(
                select(INVENTORY_DETAIL_TABLE).where(INVENTORY_DETAIL_TABLE.c.document_id == DOCUMENT_ID)
                .where(INVENTORY_DETAIL_TABLE.c.id != DETAIL_ID).order_by(INVENTORY_DETAIL_TABLE.c.id)
            ).mappings()]
            if other_order_details != unchanged_order_details or related_before != read_related_details(connection):
                raise ValueError("Other purchase details or historical documents changed")
            report["operation_log_ids"] = [
                log_change(connection, entity_type="inventory_detail", before=detail_before, after=detail_after,
                           summary=f"修正 {DOCUMENT_NUMBER} 明细 {PRODUCT_CODE}：重新关联当前商品档案，单价由 268 调整为 250.60，金额由 16080 调整为 15036（用户授权）",
                           labels=DETAIL_FIELD_LABELS),
                log_change(connection, entity_type="inventory_record", before=record_before, after=record_after,
                           summary=f"修正 {DOCUMENT_NUMBER}：商品重新关联并同步单价后，整单金额由 35160 调整为 34116（用户授权）",
                           labels=INVENTORY_FIELD_LABELS),
            ]
            report.update({"record_after": record_after, "detail_after": detail_after,
                           "other_details_unchanged": True, "quantity_and_sizes_unchanged": True})
        report["data_committed"] = True
        report["status"] = "committed"
        save_report(report)
        with engine.connect() as connection, connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '15s'"))
            final_detail = dict(connection.execute(
                select(INVENTORY_DETAIL_TABLE).where(INVENTORY_DETAIL_TABLE.c.id == DETAIL_ID)
            ).mappings().one())
            final_record = dict(connection.execute(
                select(INVENTORY_TABLE).where(INVENTORY_TABLE.c.id == DOCUMENT_ID)
            ).mappings().one())
            if final_detail != detail_after or final_record != record_after:
                raise ValueError("Post-commit verification differs from the transaction result")
        report.update({"status": "completed", "completed_at": datetime.now().astimezone().isoformat()})
        save_report(report)
        print(json.dumps(clean_payload({"status": report["status"], "document_number": DOCUMENT_NUMBER,
                                       "product_code": PRODUCT_CODE, "unit_price": final_detail["unit_price"],
                                       "detail_amount": final_detail["amount"], "order_amount": final_record["amount"],
                                       "product_identity_id": final_detail["product_identity_id"],
                                       "operation_log_ids": report["operation_log_ids"], "report": str(REPORT_PATH)}), ensure_ascii=False))
        return 0
    except Exception as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        if not REPORT_PATH.exists() or not json.loads(REPORT_PATH.read_text(encoding="utf-8")).get("data_committed"):
            save_report(report)
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
