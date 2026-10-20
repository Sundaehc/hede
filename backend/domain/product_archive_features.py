from __future__ import annotations


WOMENS_PRODUCT_STYLE_BRANDS = frozenset({
    "cbanner_womens",
    "supplier_brand_33aa8a0c3b6a",
})


def has_womens_product_style_fields(brand: str | None) -> bool:
    return brand in WOMENS_PRODUCT_STYLE_BRANDS
