from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TABLE_NAMES = {
    "qbd_mens": "qbd_mens_products",
    "qbd_womens": "qbd_womens_products",
    "yandou": "yandou_products",
    "yiban": "yiban_products",
}


IMAGE_BRAND_KEYS = {
    "qbd_mens": "qbd",
    "qbd_womens": "qbd",
    "yandou": "yandou",
    "yiban": "yiban",
}


COLUMN_ALIASES = {
    "图片": "image_path",
    "货号": "sku",
    "原始货号": "original_sku",
    "组别": "group_name",
    "成本": "cost",
    "工厂货号": "factory_sku",
    "颜色": "color",
    "新色": "color",
    "季节分类": "season_category",
    "年份": "year",
    "鞋面材质": "upper_material",
    "帮面材质": "upper_material",
    "内里材质": "lining_material",
    "大底材质": "outsole_material",
    "鞋垫材质": "insole_material",
    "执行标准": "execution_standard",
    "执行标": "execution_standard",
    "跟高": "heel_height",
    "鞋宽": "shoe_width",
    "鞋长": "shoe_length",
    "筒围": "shaft_circumference",
    "筒高": "shaft_height",
    "内增高": "internal_height_increase",
    "内增高备注": "internal_height_note",
    "鞋帮": "upper_height",
    "鞋头": "toe_shape",
    "鞋头款式": "toe_shape",
    "闭合方式": "closure_type",
    "鞋盒规格": "shoe_box_spec",
    "首单时间": "first_order_time",
    "尺码段": "size_range",
    "码段": "size_range",
    "产品型号": "product_model",
    "供应商名": "supplier_name",
    "供应商": "supplier_name",
    "颜色代码": "color_code",
    "上市时间": "launch_date",
}


CANONICAL_COLUMNS = [
    "image_path",
    "sku",
    "original_sku",
    "group_name",
    "cost",
    "factory_sku",
    "color",
    "season_category",
    "year",
    "upper_material",
    "lining_material",
    "outsole_material",
    "insole_material",
    "execution_standard",
    "heel_height",
    "shoe_width",
    "shoe_length",
    "shaft_circumference",
    "shaft_height",
    "internal_height_increase",
    "internal_height_note",
    "upper_height",
    "toe_shape",
    "closure_type",
    "shoe_box_spec",
    "first_order_time",
    "size_range",
    "product_model",
    "supplier_name",
    "color_code",
    "launch_date",
]


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
        workbook_key="qbd_mens_21_24",
        file_prefix="21-24年千百度男鞋商品资料档案新",
        brand_group="qbd_mens",
        sheets=(SheetSpec("千百度"),),
    ),
    WorkbookSpec(
        workbook_key="qbd_mens_25",
        file_prefix="25千百度男鞋商品资料档案新",
        brand_group="qbd_mens",
        sheets=(
            SheetSpec("25年春季款"),
            SheetSpec("25年夏季款"),
            SheetSpec("25年秋季款"),
            SheetSpec("25年冬季款"),
        ),
    ),
    WorkbookSpec(
        workbook_key="qbd_mens_26",
        file_prefix="26千百度商品资料表新",
        brand_group="qbd_mens",
        sheets=(
            SheetSpec("26年春季款"),
            SheetSpec("26年夏季款"),
            SheetSpec("26年秋季款", optional=True),
            SheetSpec("26年冬季款", optional=True),
        ),
    ),
    WorkbookSpec(
        workbook_key="qbd_womens",
        file_prefix="千百度女鞋商品资料档案新10",
        brand_group="qbd_womens",
        sheets=(SheetSpec("千百度"), SheetSpec("洞洞鞋", optional=True)),
    ),
    WorkbookSpec(
        workbook_key="yandou",
        file_prefix="烟斗商品资料档案新",
        brand_group="yandou",
        sheets=(SheetSpec("烟斗"),),
    ),
    WorkbookSpec(
        workbook_key="yiban",
        file_prefix="伊伴商品资料档案新（1)1",
        brand_group="yiban",
        sheets=(SheetSpec("2024"), SheetSpec("2025"), SheetSpec("2026")),
    ),
)


def workbook_specs_by_brand() -> dict[str, list[WorkbookSpec]]:
    grouped: dict[str, list[WorkbookSpec]] = {}
    for spec in WORKBOOK_SPECS:
        grouped.setdefault(spec.brand_group, []).append(spec)
    return grouped
