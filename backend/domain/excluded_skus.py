from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement, Text, all_, and_, bindparam, or_, true
from sqlalchemy.dialects.postgresql import ARRAY


EXCLUDED_SKUS_FILE = Path(__file__).with_name("excluded_skus.txt")


def normalize_sku(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _load_excluded_skus() -> frozenset[str]:
    if not EXCLUDED_SKUS_FILE.exists():
        return frozenset()
    return frozenset(
        line.strip()
        for line in EXCLUDED_SKUS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


EXCLUDED_SKUS = _load_excluded_skus()


def is_excluded_sku(*values: Any) -> bool:
    return any(normalize_sku(value) in EXCLUDED_SKUS for value in values if normalize_sku(value))


def not_excluded_sku_condition(*columns: ColumnElement[Any]) -> ColumnElement[bool]:
    if not EXCLUDED_SKUS:
        return true()
    excluded = bindparam(
        "excluded_skus",
        sorted(EXCLUDED_SKUS),
        type_=ARRAY(Text()),
    )
    return and_(
        *[
            or_(column.is_(None), column == "", column != all_(excluded))
            for column in columns
        ]
    )
