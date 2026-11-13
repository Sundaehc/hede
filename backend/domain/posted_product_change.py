"""A confirmation is bound to the exact archive change and posted-document scope."""
from __future__ import annotations

from hashlib import sha256
import json


GUARDED_PRODUCT_FIELDS = {"sku": "商品货号", "size_range": "尺码段"}


def posted_product_changes(before: dict, after: dict) -> list[dict]:
    changes = []
    for field, label in GUARDED_PRODUCT_FIELDS.items():
        old = str(before.get(field) or "").strip()
        new = str(after.get(field) or "").strip()
        if old != new:
            changes.append({"field": field, "label": label, "before": old, "after": new})
    return changes


def posted_product_change_warning(brand: str, product_id: int, changes: list[dict], documents: list[dict]) -> dict:
    fingerprint = json.dumps({"brand": brand, "product_id": product_id, "changes": changes,
                              "documents": sorted((row["id"], row["detail_count"]) for row in documents)},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "code": "posted_product_change_confirmation",
        "message": f"该商品已在 {len(documents)} 张经营历程单据中过账，是否继续变更？",
        "confirmation_token": sha256(fingerprint.encode("utf-8")).hexdigest(),
        "changes": changes, "documents": documents,
        "document_count": len(documents), "detail_count": sum(row["detail_count"] for row in documents),
    }
