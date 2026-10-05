from __future__ import annotations

from collections.abc import MutableMapping


CBANNER_WOMENS_DEFAULT_GROUP_NAME = "女鞋"
SMILEY_DEFAULT_SIZE_RANGE = "笑脸女鞋34-40"
BARCODE_COLOR_SIZE_RULE = "货号+颜色代码+尺码"
BARCODE_SIZE_RULE = "货号+尺码"
COLOR_SIZE_BARCODE_BRANDS = {"cbanner_mens", "cbanner_womens", "eblan"}
SIZE_ONLY_BARCODE_BRANDS = {"smiley", "ni"}


def smiley_color_code(sku: object) -> str:
    return str(sku or "").strip()[-4:]


def fixed_barcode_build_rule(
    brand_group: str,
    sku: object = None,
    original_sku: object = None,
) -> str | None:
    normalized_brand = str(brand_group or "").strip().lower()
    code = str(sku or original_sku or "").strip().upper()
    if normalized_brand in SIZE_ONLY_BARCODE_BRANDS or code.startswith("KT"):
        return BARCODE_SIZE_RULE
    if normalized_brand in COLOR_SIZE_BARCODE_BRANDS:
        return BARCODE_COLOR_SIZE_RULE
    return None


def apply_product_defaults(brand_group: str, row: MutableMapping[str, object]) -> MutableMapping[str, object]:
    if brand_group == "cbanner_womens":
        group_name = row.get("group_name")
        if group_name is None or not str(group_name).strip():
            row["group_name"] = CBANNER_WOMENS_DEFAULT_GROUP_NAME
    if brand_group == "smiley" and not str(row.get("size_range") or "").strip():
        row["size_range"] = SMILEY_DEFAULT_SIZE_RANGE
    barcode_rule = fixed_barcode_build_rule(
        brand_group,
        row.get("sku"),
        row.get("original_sku"),
    )
    if barcode_rule:
        row["barcode_build_rule"] = barcode_rule
    return row
