from __future__ import annotations

from collections import defaultdict
import re


def shop_channel_key(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def platform_name(channel: object, shop_channel_mappings: dict[str, str] | None = None) -> str:
    value = str(channel or "").strip()
    mapped_channel = (shop_channel_mappings or {}).get(shop_channel_key(value))
    if mapped_channel:
        return mapped_channel
    if "唯品" in value:
        return "唯品"
    if "天猫" in value:
        return "天猫"
    if "得物" in value:
        return "得物"
    if "拼多多" in value and "清仓" in value:
        return "拼多多清仓"
    if "拼多多" in value:
        return "拼多多"
    if "京东" in value:
        return "京东"
    if "商品卡" in value:
        return "商品卡"
    if "达播" in value and "清仓" in value:
        return "达播清仓"
    if "直播" in value:
        return "直播赛道"
    return "其他"


def is_clearance_channel(channel: object, platform: str) -> bool:
    return "清仓" in str(channel or "") or platform in {"达播清仓", "拼多多清仓"}


def channel_group(channel: object, shop_channel_mappings: dict[str, str]) -> str:
    platform = platform_name(channel, shop_channel_mappings)
    if is_clearance_channel(channel, platform):
        return "clearance"
    if platform == "直播赛道":
        return "live"
    return "traditional"


def sales_metrics(row: dict[str, object] | object) -> tuple[int, int, int]:
    """Return net quantity, gross sales quantity and return quantity."""
    values = row if isinstance(row, dict) else {}
    net_quantity = int(values.get("quantity") or 0)
    gross_value = values.get("gross_quantity")
    return_value = values.get("return_quantity")
    gross_quantity = max(net_quantity, 0) if gross_value is None else max(int(gross_value or 0), 0)
    return_quantity = max(-net_quantity, 0) if return_value is None else max(int(return_value or 0), 0)
    return net_quantity, gross_quantity, return_quantity


def season_group(value: object) -> str | None:
    normalized = re.sub(r"\s+", "", str(value or "").strip())
    if "春夏" in normalized or "春" in normalized or "夏" in normalized:
        return "spring_summer"
    if "秋冬" in normalized or "秋" in normalized or "冬" in normalized:
        return "autumn_winter"
    return None


def product_index(rows: list[dict[str, object]]) -> tuple[
    dict[str, dict[str, object]],
    dict[str, list[dict[str, object]]],
    dict[str, str],
]:
    by_sku: dict[str, dict[str, object]] = {}
    by_prefix: dict[str, list[dict[str, object]]] = defaultdict(list)
    style_matches: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        by_sku[sku] = row
        by_prefix[sku[:4]].append(row)
        style_code = str(row.get("original_sku") or "").strip()
        if style_code:
            style_matches[style_code].append(sku)
    for candidates in by_prefix.values():
        candidates.sort(key=lambda item: len(str(item.get("sku") or "")), reverse=True)
    unique_style_matches = {
        style_code: skus[0]
        for style_code, skus in style_matches.items()
        if len(skus) == 1
    }
    return by_sku, by_prefix, unique_style_matches


def product_for_sale(
    product_code: object,
    style_code: object,
    *,
    by_sku: dict[str, dict[str, object]],
    by_prefix: dict[str, list[dict[str, object]]],
    unique_style_matches: dict[str, str],
) -> dict[str, object] | None:
    code = str(product_code or "").strip()
    if code:
        exact = by_sku.get(code)
        if exact is not None:
            return exact
        for candidate in by_prefix.get(code[:4], []):
            sku = str(candidate.get("sku") or "").strip()
            if sku and code.startswith(sku):
                return candidate
    matched_sku = unique_style_matches.get(str(style_code or "").strip())
    return by_sku.get(matched_sku) if matched_sku else None
