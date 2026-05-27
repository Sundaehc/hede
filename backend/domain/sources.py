from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.fields import PRODUCT_FIELDS, alias_map, field_names


TABLE_NAMES = {
    "cbanner_mens": "cbanner_mens_products",
    "cbanner_womens": "cbanner_womens_products",
    "yandou": "yandou_products",
    "eblan": "eblan_products",
}


IMAGE_BRAND_KEYS = {
    "cbanner_mens": "cbanner",
    "cbanner_womens": "cbanner",
    "yandou": "yandou",
    "eblan": "eblan",
}


COLUMN_ALIASES = alias_map(PRODUCT_FIELDS)


CANONICAL_COLUMNS = field_names(PRODUCT_FIELDS)


@dataclass(frozen=True)
class SheetSpec:
    name: str
    optional: bool = False


@dataclass(frozen=True)
class WorkbookSpec:
    workbook_key: str
    file_prefix: str
    brand_group: str
    sheets: tuple[SheetSpec, ...]

    def matching_extensions(self) -> tuple[str, ...]:
        return (".xlsx", ".xlsm", ".xls")

    def resolve_path(self, root: Path) -> Path:
        candidates: list[Path] = []
        for extension in self.matching_extensions():
            candidates.extend(sorted(root.glob(f"{self.file_prefix}*{extension}")))

        if not candidates:
            raise FileNotFoundError(f"Workbook not found for prefix: {self.file_prefix}")

        return candidates[0]


WORKBOOK_SPECS = (
    WorkbookSpec(
        workbook_key="cbanner_mens_21_24",
        file_prefix="21-24年千百度男鞋商品资料档案新",
        brand_group="cbanner_mens",
        sheets=(SheetSpec("千百度"),),
    ),
    WorkbookSpec(
        workbook_key="cbanner_mens_25",
        file_prefix="25千百度男鞋商品资料档案新",
        brand_group="cbanner_mens",
        sheets=(
            SheetSpec("25年春季款"),
            SheetSpec("25年夏季款"),
            SheetSpec("25年秋季款"),
            SheetSpec("25年冬季款"),
        ),
    ),
    WorkbookSpec(
        workbook_key="cbanner_mens_26",
        file_prefix="26千百度商品资料表新",
        brand_group="cbanner_mens",
        sheets=(
            SheetSpec("26年春季款"),
            SheetSpec("26年夏季款"),
            SheetSpec("26年秋季款", optional=True),
            SheetSpec("26年冬季款", optional=True),
        ),
    ),
    WorkbookSpec(
        workbook_key="cbanner_womens",
        file_prefix="千百度女鞋商品资料档案新10",
        brand_group="cbanner_womens",
        sheets=(SheetSpec("千百度"), SheetSpec("洞洞鞋", optional=True)),
    ),
    WorkbookSpec(
        workbook_key="yandou",
        file_prefix="烟斗商品资料档案新",
        brand_group="yandou",
        sheets=(SheetSpec("烟斗"),),
    ),
    WorkbookSpec(
        workbook_key="eblan",
        file_prefix="伊伴商品资料档案新（1)1",
        brand_group="eblan",
        sheets=(SheetSpec("2024"), SheetSpec("2025"), SheetSpec("2026")),
    ),
)


def workbook_specs_by_brand() -> dict[str, list[WorkbookSpec]]:
    grouped: dict[str, list[WorkbookSpec]] = {}
    for spec in WORKBOOK_SPECS:
        grouped.setdefault(spec.brand_group, []).append(spec)
    return grouped
