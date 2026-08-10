from __future__ import annotations

from collections.abc import MutableMapping


CBANNER_WOMENS_DEFAULT_GROUP_NAME = "女鞋"
COLOR_AND_SIZE_BARCODE_BRANDS = {"cbanner_mens", "cbanner_womens", "eblan"}
SIZE_ONLY_BARCODE_BRANDS = {"ni", "smiley"}
COLOR_AND_SIZE_BARCODE_RULE = "货号+颜色代码+尺码"
SIZE_ONLY_BARCODE_RULE = "货号+尺码"


def _uses_sku_and_size_barcode_rule(row: MutableMapping[str, object]) -> bool:
    return any(
        str(row.get(field) or "").strip().upper().startswith("KT")
        for field in ("sku", "original_sku")
    )


def barcode_build_rule_for_product(
    brand_group: object,
    row: MutableMapping[str, object],
) -> str | None:
    normalized_brand = str(brand_group or "").strip().lower()
    if normalized_brand in SIZE_ONLY_BARCODE_BRANDS or _uses_sku_and_size_barcode_rule(row):
        return SIZE_ONLY_BARCODE_RULE
    if normalized_brand in COLOR_AND_SIZE_BARCODE_BRANDS:
        return COLOR_AND_SIZE_BARCODE_RULE
    return None


def apply_product_defaults(brand_group: str, row: MutableMapping[str, object]) -> MutableMapping[str, object]:
    if brand_group == "cbanner_womens":
        group_name = row.get("group_name")
        if group_name is None or not str(group_name).strip():
            row["group_name"] = CBANNER_WOMENS_DEFAULT_GROUP_NAME
    if barcode_build_rule := barcode_build_rule_for_product(brand_group, row):
        row["barcode_build_rule"] = barcode_build_rule
    return row
