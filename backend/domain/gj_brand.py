from __future__ import annotations

CBANNER_MENS_BRAND = "cbanner_mens"
CBANNER_WOMENS_BRAND = "cbanner_womens"
YANDOU_BRAND = "yandou"
EBLAN_BRAND = "eblan"
SMILEY_BRAND = "smiley"

GJ_FINE_TABLE_BRANDS = {
    CBANNER_MENS_BRAND,
    CBANNER_WOMENS_BRAND,
    YANDOU_BRAND,
    EBLAN_BRAND,
    SMILEY_BRAND,
}


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def infer_gj_fine_table_brand(row: dict[str, object]) -> str | None:
    brand = _clean(row.get("brand"))
    brand_upper = brand.upper()
    supplier = _clean(row.get("primary_supplier"))

    if "TRUMPPIPE" in brand_upper or "烟斗" in brand:
        return YANDOU_BRAND
    if "EBLAN" in brand_upper or "伊伴" in brand:
        return EBLAN_BRAND

    return infer_supplier_brand_from_name(supplier)


def infer_supplier_brand_from_name(name: object) -> str | None:
    supplier = _clean(name)
    supplier_upper = supplier.upper()
    if "SMILEY" in supplier_upper or "笑脸" in supplier or "小莲" in supplier:
        return SMILEY_BRAND
    if "TRUMPPIPE" in supplier_upper or "烟斗" in supplier:
        return YANDOU_BRAND
    if "EBLAN" in supplier_upper or "伊伴" in supplier:
        return EBLAN_BRAND
    if "千百度品牌方" in supplier:
        return None
    if "千百度女鞋" in supplier:
        return CBANNER_WOMENS_BRAND
    if "千百度" not in supplier:
        return None
    return CBANNER_MENS_BRAND


def normalize_gj_fine_table_brand(value: object) -> str | None:
    brand = _clean(value)
    return brand if brand in GJ_FINE_TABLE_BRANDS else None
