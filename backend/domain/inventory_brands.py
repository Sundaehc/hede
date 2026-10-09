from __future__ import annotations

from collections.abc import Iterable, Mapping


INVENTORY_BRAND_LABELS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "yandou": "烟斗",
    "eblan": "伊伴男鞋",
    "eblan_womens": "伊伴女鞋",
    "smiley": "笑脸",
    "ni": "NI",
    "ns": "NS",
}

INVENTORY_BRAND_ALIASES = {
    "cbanner_mens": ("千百度", "千百度男鞋"),
    "cbanner_womens": ("千百度女鞋",),
    "yandou": ("烟斗",),
    "eblan": ("伊伴", "伊伴男鞋"),
    "eblan_womens": ("伊伴女鞋",),
    "smiley": ("笑脸", "SMILEY"),
    "ni": ("NI",),
    "ns": ("NS",),
}


def inventory_brand_key(value: object, groups: Mapping[str, set[str]]) -> str:
    name = str(value or "").strip()
    normalized = name.casefold()
    for code, aliases in groups.items():
        if any(alias.casefold() == normalized for alias in aliases):
            return code
    return name.removesuffix("仓库") or name


def inventory_brand_groups(supplier_brands: Iterable[Mapping[str, object]]) -> dict[str, set[str]]:
    groups = {
        code: {code, *names, *(f"{name}仓库" for name in names)}
        for code, names in INVENTORY_BRAND_ALIASES.items()
    }
    for brand in supplier_brands:
        code = str(brand.get("code") or "").strip()
        name = str(brand.get("name") or "").strip()
        if not code:
            continue
        key = inventory_brand_key(code, groups)
        aliases = groups.setdefault(key, set())
        aliases.add(code)
        if name:
            aliases.update((name, f"{name}仓库"))
    return groups


def inventory_brand_filter_aliases(values: Iterable[str], supplier_brands: Iterable[Mapping[str, object]]) -> list[str]:
    groups = inventory_brand_groups(supplier_brands)
    aliases: set[str] = set()
    for value in values:
        name = str(value or "").strip()
        if not name:
            continue
        key = inventory_brand_key(name, groups)
        aliases.update(groups.get(key, {key, f"{key}仓库"}))
        aliases.add(name)
    return sorted({alias.casefold() for alias in aliases})


def inventory_brand_options(
    warehouse_brands: Iterable[str],
    supplier_brands: Iterable[Mapping[str, object]],
    customer_brands: Iterable[str],
) -> list[dict[str, str]]:
    suppliers = list(supplier_brands)
    groups = inventory_brand_groups(suppliers)
    labels = dict(INVENTORY_BRAND_LABELS)
    for brand in suppliers:
        name = str(brand.get("name") or "").strip()
        if name:
            labels[inventory_brand_key(brand.get("code"), groups)] = name
    values = [*warehouse_brands, *(str(brand.get("code") or "") for brand in suppliers), *customer_brands]
    options: dict[str, dict[str, str]] = {}
    for value in values:
        key = inventory_brand_key(value, groups)
        if key and key not in options:
            options[key] = {"value": key, "label": labels.get(key, key)}
    return list(options.values())
