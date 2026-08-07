from __future__ import annotations

from collections.abc import MutableMapping


CBANNER_WOMENS_DEFAULT_GROUP_NAME = "女鞋"


def _uses_sku_and_size_barcode_rule(row: MutableMapping[str, object]) -> bool:
    return any(
        str(row.get(field) or "").strip().upper().startswith("KT")
        for field in ("sku", "original_sku")
    )


def apply_product_defaults(brand_group: str, row: MutableMapping[str, object]) -> MutableMapping[str, object]:
    if brand_group == "cbanner_womens":
        group_name = row.get("group_name")
        if group_name is None or not str(group_name).strip():
            row["group_name"] = CBANNER_WOMENS_DEFAULT_GROUP_NAME
    if brand_group in {"ni", "smiley"} or _uses_sku_and_size_barcode_rule(row):
        row["barcode_build_rule"] = "货号+尺码"
    return row
