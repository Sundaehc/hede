"""Readable, bounded SQL identifiers for manually added product brands."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection


LEGACY_ARCHIVE_PATTERN = r"^manual_product_archive_[0-9]+$"
NAMED_ARCHIVE_PATTERN = r"^[a-z][a-z0-9_]*_products$"
MANUAL_ARCHIVE_PATTERN = rf"({LEGACY_ARCHIVE_PATTERN}|{NAMED_ARCHIVE_PATTERN})"
MAX_ARCHIVE_TABLE_LENGTH = 40  # Leave room for the longest index/constraint suffix.
BRAND_PREFIXES = {"千百度": "cbanner", "伊伴": "eblan", "烟斗": "yandou", "笑脸": "smiley"}


def manual_product_table_name(value: object) -> str | None:
    name = str(value or "").strip()
    if len(name) <= 63 and re.fullmatch(MANUAL_ARCHIVE_PATTERN, name, flags=re.ASCII):
        return name
    return None


def readable_product_table_name(name: str, brand_id: int, occupied: Collection[str] = ()) -> str:
    """Keep brand names readable; append the stable ID only for collisions."""
    from pypinyin import lazy_pinyin

    normalized = unicodedata.normalize("NFKC", name).strip()
    parts = []
    for prefix, english in BRAND_PREFIXES.items():
        if normalized.startswith(prefix):
            parts.append(english)
            normalized = normalized[len(prefix):]
            break
    parts.append("".join(lazy_pinyin(normalized, errors=lambda value: [value])))
    stem = re.sub(r"[^a-z0-9]+", "_", "_".join(parts).lower()).strip("_")
    if not stem:
        stem = f"brand_{brand_id}"
    elif stem[0].isdigit():
        stem = "brand_" + stem
    stem = stem[:MAX_ARCHIVE_TABLE_LENGTH - len("_products")].rstrip("_")
    candidate = f"{stem}_products"
    attempt = 0
    while candidate in occupied:
        suffix = f"_{brand_id}" + (f"_{attempt}" if attempt else "")
        trimmed = stem[:MAX_ARCHIVE_TABLE_LENGTH - len(suffix) - len("_products")].rstrip("_")
        candidate = f"{trimmed}{suffix}_products"
        attempt += 1
    return candidate
