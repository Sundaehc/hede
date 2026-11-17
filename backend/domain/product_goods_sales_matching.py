"""Resolve sales against the complete archive, independently of visible rows."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping


def sales_brand_family(value: object) -> str | None:
    name = str(value or "").strip().upper()
    if "TRUMPPIPE" in name or "烟斗" in name:
        return "yandou"
    if "EBLAN" in name or "伊伴" in name or name == "10006686":
        return "eblan"
    if "千百度" in name or "BANNER" in name or name == "10001135":
        return "cbanner"
    if "SMILEY" in name or "笑脸" in name:
        return "smiley"
    if name in {"NS", "NI"}:
        return name.lower()
    return None


def archive_brand_family(brand: str) -> str:
    return "cbanner" if brand.startswith("cbanner_") else "eblan" if brand.startswith("eblan") else brand


class GoodsSalesCatalog:
    def __init__(self, rows: Iterable[Mapping[str, object]]):
        self.goods: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self.styles: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for row in rows:
            brand = str(row.get("brand") or "").strip()
            sku = str(row.get("sku") or "").strip()
            style = str(row.get("original_sku") or "").strip()
            if not brand or not sku:
                continue
            self.goods[sku].add((brand, sku))
            if style:
                self.styles[style].add((brand, sku))

    def style_target(self, style: str) -> tuple[str, str] | None:
        # An archive's actual goods code wins over another product's alias.
        matches = self.goods.get(style) or self.styles.get(style, set())
        return next(iter(matches)) if len(matches) == 1 else None

    def matcher(self, brand: str, products: Mapping[str, str]) -> GoodsSalesMatcher:
        return GoodsSalesMatcher(self, brand, products)


class GoodsSalesMatcher:
    def __init__(self, catalog: GoodsSalesCatalog, brand: str, products: Mapping[str, str]):
        self.catalog = catalog
        self.brand = brand
        self.products = set(products)
        self.unique_styles = {
            style: target[1]
            for style in set(products.values()) if style
            if (target := catalog.style_target(style)) is not None
            and target[0] == brand and target[1] in self.products
        }

    def resolve(self, product_code: object, style_code: object, *source_brands: object) -> str | None:
        family = archive_brand_family(self.brand)
        if any((source := sales_brand_family(value)) is not None and source != family for value in source_brands):
            return None
        code = str(product_code or "").strip()
        for end in range(len(code), 0, -1):
            matches = self.catalog.goods.get(code[:end])
            if not matches:
                continue
            # Do not fall back to a shorter or aliased product when a more
            # specific archive entry belongs to a different product/brand.
            if len(matches) != 1:
                return None
            matched_brand, sku = next(iter(matches))
            return sku if matched_brand == self.brand and sku in self.products else None
        return self.unique_styles.get(str(style_code or "").strip())
