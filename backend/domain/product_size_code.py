from __future__ import annotations

from domain.product_defaults import barcode_build_rule_for_product


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def build_product_size_code(
    goods_code: object,
    color_code: object,
    size_barcode: object,
    barcode_build_rule: object,
    *,
    brand: object = None,
    original_goods_code: object = None,
) -> str:
    normalized_goods_code = _text(goods_code)
    if not normalized_goods_code:
        return ""

    normalized_size_barcode = _text(size_barcode)
    normalized_color_code = _text(color_code)
    enforced_rule = barcode_build_rule_for_product(
        brand,
        {
            "sku": normalized_goods_code,
            "original_sku": _text(original_goods_code),
        },
    )
    effective_rule = enforced_rule or _text(barcode_build_rule)
    if effective_rule != "货号+尺码" and normalized_color_code:
        return f"{normalized_goods_code}{normalized_color_code}{normalized_size_barcode}"
    return f"{normalized_goods_code}{normalized_size_barcode}"
