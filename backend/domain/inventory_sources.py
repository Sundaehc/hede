from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.fields import (
    GENERAL_CUSTOMER_BRAND_FIELDS,
    GENERAL_CUSTOMER_SHOP_FIELDS,
    INVENTORY_DETAIL_FIELDS,
    INVENTORY_FIELDS,
    JST_STOCK_FIELDS,
    SUPPLIER_FIELDS,
    WAREHOUSE_FIELDS,
    alias_map,
    field_names,
)

INVENTORY_TABLE_NAME = "inventory_records"
SUPPLIER_TABLE_NAME = "suppliers"
WAREHOUSE_TABLE_NAME = "warehouses"
GENERAL_CUSTOMER_BRAND_TABLE_NAME = "general_customer_brands"
GENERAL_CUSTOMER_SHOP_TABLE_NAME = "general_customer_shops"
INVENTORY_DETAIL_TABLE_NAME = "inventory_details"
JST_STOCK_TABLE_NAME = "jst_daily_stock"

JST_STOCK_COLUMNS = field_names(JST_STOCK_FIELDS)

# Column aliases for Excel import: Chinese header -> canonical field name
INVENTORY_COLUMN_ALIASES: dict[str, str] = alias_map(INVENTORY_FIELDS)

# Canonical fields for the inventory_records table
INVENTORY_CANONICAL_COLUMNS: list[str] = field_names(INVENTORY_FIELDS)

# Detail table canonical fields
INVENTORY_DETAIL_COLUMNS: list[str] = field_names(INVENTORY_DETAIL_FIELDS)

# Detail column aliases for Excel import
INVENTORY_DETAIL_ALIASES: dict[str, str] = alias_map(INVENTORY_DETAIL_FIELDS)

# Document type choices
DOCUMENT_TYPES: tuple[str, ...] = (
    "进货单",
    "进货退货单",
    "报溢单",
    "报损单",
    "批发销售单",
    "批发销售退货单",
    "同价调拨单",
)

DOCUMENT_TYPE_ALIASES: dict[str, str] = {
    "工厂进货单": "进货单",
    "工厂退货单": "进货退货单",
}


def normalize_document_type(value: object) -> str:
    document_type = "" if value is None else str(value).strip()
    return DOCUMENT_TYPE_ALIASES.get(document_type, document_type)

SUPPLIER_COLUMNS: list[str] = field_names(SUPPLIER_FIELDS)

WAREHOUSE_COLUMNS: list[str] = field_names(WAREHOUSE_FIELDS)

GENERAL_CUSTOMER_BRAND_COLUMNS: list[str] = field_names(GENERAL_CUSTOMER_BRAND_FIELDS)

GENERAL_CUSTOMER_SHOP_COLUMNS: list[str] = field_names(GENERAL_CUSTOMER_SHOP_FIELDS)

# Excel export labels (Chinese)
INVENTORY_EXPORT_LABELS: dict[str, str] = {
    field.name: field.label for field in INVENTORY_FIELDS
}


@dataclass(frozen=True)
class InventorySheetSpec:
    name: str
    optional: bool = False


@dataclass(frozen=True)
class InventoryWorkbookSpec:
    file_prefix: str
    sheets: tuple[InventorySheetSpec, ...]

    def matching_extensions(self) -> tuple[str, ...]:
        return (".xlsx", ".xlsm", ".xls")

    def resolve_path(self, root: Path) -> Path:
        candidates: list[Path] = []
        for extension in self.matching_extensions():
            candidates.extend(sorted(root.glob(f"{self.file_prefix}*{extension}")))

        if not candidates:
            raise FileNotFoundError(f"Workbook not found for prefix: {self.file_prefix}")

        return candidates[0]
