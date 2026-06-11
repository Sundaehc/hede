from __future__ import annotations

CBANNER_MENS_BRAND = "cbanner_mens"
CBANNER_WOMENS_BRAND = "cbanner_womens"
YANDOU_BRAND = "yandou"
EBLAN_BRAND = "eblan"

GJ_FINE_TABLE_BRANDS = {
    CBANNER_MENS_BRAND,
    CBANNER_WOMENS_BRAND,
    YANDOU_BRAND,
    EBLAN_BRAND,
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

    if "千百度品牌方" in supplier or "千百度" not in supplier:
        return None
    if "千百度女鞋" in supplier:
        return CBANNER_WOMENS_BRAND
    return CBANNER_MENS_BRAND


def normalize_gj_fine_table_brand(value: object) -> str | None:
    brand = _clean(value)
    return brand if brand in GJ_FINE_TABLE_BRANDS else None
