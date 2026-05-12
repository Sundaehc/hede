from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

INVENTORY_TABLE_NAME = "inventory_records"
SUPPLIER_TABLE_NAME = "suppliers"
WAREHOUSE_TABLE_NAME = "warehouses"

# Column aliases for Excel import: Chinese header -> canonical field name
INVENTORY_COLUMN_ALIASES: dict[str, str] = {
    "日期": "date",
    "供应商": "supplier",
    "商品编码": "product_code",
    "数量": "quantity",
    "单价": "unit_price",
    "仓库": "warehouse",
    "单据类型": "document_type",
    "摘要": "summary",
}

# Canonical fields for the inventory_records table
INVENTORY_CANONICAL_COLUMNS: list[str] = [
    "date",
    "supplier",
    "product_code",
    "quantity",
    "unit_price",
    "warehouse",
    "document_type",
    "summary",
]

# Document type choices
DOCUMENT_TYPES: tuple[str, ...] = ("工厂进货单", "工厂退货单")

SUPPLIER_COLUMNS: list[str] = [
    "name",
    "contact",
    "address",
    "notes",
]

WAREHOUSE_COLUMNS: list[str] = [
    "name",
    "address",
    "notes",
]

# Excel export labels (Chinese)
INVENTORY_EXPORT_LABELS: dict[str, str] = {
    "date": "日期",
    "supplier": "供应商",
    "product_code": "商品编码",
    "quantity": "数量",
    "unit_price": "单价",
    "warehouse": "仓库",
    "document_type": "单据类型",
    "summary": "摘要",
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
