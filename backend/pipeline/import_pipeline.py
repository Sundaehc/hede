from __future__ import annotations

from dataclasses import dataclass
import re

from config import Settings
from domain.excluded_skus import is_excluded_sku
from domain.gj_schema import GJ_MERGED_PRODUCT_INFO_TABLE
from domain.sources import IMAGE_BRAND_KEYS, WORKBOOK_SPECS
from domain.sources import CANONICAL_COLUMNS
from fileio.cbanner_mens_group_reader import read_cbanner_mens_group_map
from fileio.excel_reader import read_workbook_rows
from fileio.image_matcher import ImageMatcher
from storage.date_normalization import parse_date
from storage.db import Database
from transform.rows import build_canonical_row
from sqlalchemy import func, select


@dataclass
class ImportSummary:
    brand_group: str
    extracted_rows: int = 0
    loaded_rows: int = 0
    skipped_rows: int = 0
    missing_images: int = 0


CBANNER_BRANDS = {"cbanner_mens", "cbanner_womens"}
GJ_PRODUCT_BRANDS = {*CBANNER_BRANDS, "yandou", "eblan"}
GJ_ARCHIVE_SUPPLEMENT_FIELDS = {
    "image_path",
    "group_name",
    "cost",
    "color",
    "season_category",
    "year",
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
    "first_order_time",
    "size_range",
    "color_code",
}


def _clean_code(value: object) -> str:
    return "" if value is None else str(value).strip()


def _date_text(value: object) -> str | None:
    parsed = parse_date(value)
    if parsed is not None:
        return parsed.isoformat()
    text = _clean_code(value)
    return text or None


def _codes_for_archive_match(row: dict[str, object]) -> set[str]:
    return {
        code
        for code in (
            _clean_code(row.get("sku")),
            _clean_code(row.get("original_sku")),
        )
        if code
    }


def _is_cbanner_womens_supplier(value: object) -> bool:
    supplier = _clean_code(value)
    return re.search(r"[（(][^）)]*千百度女鞋", supplier) is not None


def _is_cbanner_brand_owner_supplier(value: object) -> bool:
    supplier = _clean_code(value)
    return "千百度品牌方" in supplier


def _cbanner_brand_from_gj_row(row: dict[str, object]) -> str | None:
    supplier = _clean_code(row.get("primary_supplier"))
    if "千百度" not in supplier:
        return None
    if _is_cbanner_brand_owner_supplier(supplier):
        return None
    return "cbanner_womens" if _is_cbanner_womens_supplier(supplier) else "cbanner_mens"


def _brand_from_gj_row(row: dict[str, object]) -> str | None:
    brand = _clean_code(row.get("brand"))
    if "TRUMPPIPE" in brand:
        return "yandou"
    if "EBLAN" in brand or "伊伴" in brand:
        return "eblan"
    return _cbanner_brand_from_gj_row(row)


def _archive_group_key(brand_group: str) -> str:
    return "cbanner" if brand_group in CBANNER_BRANDS else brand_group


def _merge_extra_fields(*values: object) -> dict[str, object] | None:
    merged: dict[str, object] = {}
    for value in values:
        if isinstance(value, dict):
            merged.update(value)
    return merged or None


def _gj_row_to_product_row(
    row: dict[str, object],
    *,
    brand_group: str,
    archive_row: dict[str, object] | None,
    image_path: str | None,
) -> dict[str, object] | None:
    goods_code = _clean_code(row.get("goods_code"))
    if not goods_code:
        return None

    original_goods_code = _clean_code(row.get("original_goods_code")) or goods_code
    if is_excluded_sku(goods_code, original_goods_code):
        return None

    canonical = {column: None for column in CANONICAL_COLUMNS}
    canonical.update({
        "image_path": image_path,
        "sku": goods_code,
        "original_sku": original_goods_code,
        "factory_sku": row.get("factory_code"),
        "upper_material": row.get("upper_material"),
        "lining_material": row.get("lining_material"),
        "outsole_material": row.get("outsole_material"),
        "insole_material": row.get("insole_material"),
        "execution_standard": row.get("execution_standard"),
        "shoe_box_spec": row.get("shoe_box_spec"),
        "product_model": row.get("product_name"),
        "supplier_name": row.get("primary_supplier"),
        "launch_date": _date_text(row.get("launch_date")),
    })

    if archive_row is not None:
        for field in GJ_ARCHIVE_SUPPLEMENT_FIELDS:
            if canonical.get(field) in (None, ""):
                canonical[field] = archive_row.get(field)

    return {
        **canonical,
        "source_workbook": row.get("source_workbook") or "gj_merged_product_info",
        "source_sheet": row.get("source_sheet") or brand_group,
        "source_row_number": str(row.get("source_row_number") or ""),
        "raw_payload": row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {},
        "extra_fields": _merge_extra_fields(
            archive_row.get("extra_fields") if archive_row else None,
            row.get("extra_fields"),
        ),
    }


class ImportPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.database = Database(settings.database_url)
        self.image_matchers = {
            brand_key: ImageMatcher(root)
            for brand_key, root in settings.image_roots.items()
        }

    def run(self, *, dry_run: bool, mode: str = "replace") -> dict[str, ImportSummary]:
        summaries = {
            brand_group: ImportSummary(brand_group=brand_group)
            for brand_group in {spec.brand_group for spec in WORKBOOK_SPECS}
        }
        rows_by_brand: dict[str, list[dict[str, object]]] = {key: [] for key in summaries}
        archive_by_group_and_code: dict[str, dict[str, dict[str, object]]] = {
            _archive_group_key(brand_group): {}
            for brand_group in GJ_PRODUCT_BRANDS
        }

        for spec in WORKBOOK_SPECS:
            workbook_path = spec.resolve_path(self.settings.excel_root)
            workbook_name = workbook_path.stem
            sheet_rows_map = read_workbook_rows(spec, self.settings.excel_root)
            matcher = self.image_matchers[IMAGE_BRAND_KEYS[spec.brand_group]]
            for sheet_name, sheet_rows in sheet_rows_map.items():
                for index, raw_row in enumerate(sheet_rows, start=2):
                    summaries[spec.brand_group].extracted_rows += 1
                    original_sku = raw_row.get("原始货号") or raw_row.get("货号")
                    image_path = matcher.find(original_sku)

                    canonical = build_canonical_row(
                        raw_row,
                        workbook_key=workbook_name,
                        sheet_name=sheet_name,
                        row_number=index,
                        image_path=image_path,
                    )
                    if canonical is None:
                        summaries[spec.brand_group].skipped_rows += 1
                        continue
                    if is_excluded_sku(canonical.get("sku"), canonical.get("original_sku")):
                        summaries[spec.brand_group].skipped_rows += 1
                        continue
                    if image_path is None:
                        summaries[spec.brand_group].missing_images += 1
                    if spec.brand_group in GJ_PRODUCT_BRANDS:
                        archive_key = _archive_group_key(spec.brand_group)
                        for code in _codes_for_archive_match(canonical):
                            archive_by_group_and_code.setdefault(archive_key, {})[code] = canonical
                    else:
                        rows_by_brand[spec.brand_group].append(canonical)

        cbanner_mens_group_by_code = read_cbanner_mens_group_map(self.settings.cbanner_mens_group_source)
        gj_rows_by_brand = self._build_product_rows_from_gj(
            archive_by_group_and_code,
            cbanner_mens_group_by_code=cbanner_mens_group_by_code,
        )
        for brand_group in GJ_PRODUCT_BRANDS:
            rows_by_brand[brand_group] = gj_rows_by_brand.get(brand_group, [])
            summaries[brand_group].loaded_rows = len(rows_by_brand[brand_group])
            summaries[brand_group].missing_images = sum(
                1
                for row in rows_by_brand[brand_group]
                if row.get("image_path") is None
            )

        if not dry_run:
            self.database.create_tables()
            for brand_group, rows in rows_by_brand.items():
                if mode == "sync" and brand_group not in GJ_PRODUCT_BRANDS:
                    summaries[brand_group].loaded_rows = self.database.upsert_brand_rows(brand_group, rows)
                else:
                    summaries[brand_group].loaded_rows = self.database.replace_brand_rows(brand_group, rows)
        else:
            for brand_group, rows in rows_by_brand.items():
                summaries[brand_group].loaded_rows = len(rows)

        return summaries

    def _build_product_rows_from_gj(
        self,
        archive_by_group_and_code: dict[str, dict[str, dict[str, object]]],
        *,
        cbanner_mens_group_by_code: dict[str, str] | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        if self.database.engine is None:
            raise ValueError("DATABASE_URL is required to import products from gj_merged_product_info")

        rows_by_brand: dict[str, list[dict[str, object]]] = {brand: [] for brand in GJ_PRODUCT_BRANDS}

        with self.database.engine.connect() as connection:
            latest_source_date = connection.execute(
                select(func.max(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value))
            ).scalar()
            if latest_source_date is None:
                return rows_by_brand

            rows = connection.execute(
                select(GJ_MERGED_PRODUCT_INFO_TABLE)
                .where(GJ_MERGED_PRODUCT_INFO_TABLE.c.source_date_value == latest_source_date)
                .order_by(GJ_MERGED_PRODUCT_INFO_TABLE.c.row_no, GJ_MERGED_PRODUCT_INFO_TABLE.c.id)
            ).mappings()

            for row_mapping in rows:
                row = dict(row_mapping)
                brand_group = _brand_from_gj_row(row)
                if brand_group is None:
                    continue

                match_codes = [
                    _clean_code(row.get("goods_code")),
                    _clean_code(row.get("original_goods_code")),
                ]
                if is_excluded_sku(*match_codes):
                    continue
                archive_key = _archive_group_key(brand_group)
                archive_by_code = archive_by_group_and_code.get(archive_key, {})
                archive_row = next(
                    (archive_by_code[code] for code in match_codes if code and code in archive_by_code),
                    None,
                )
                cbanner_mens_group_name = None
                if brand_group == "cbanner_mens" and cbanner_mens_group_by_code:
                    cbanner_mens_group_name = next(
                        (
                            cbanner_mens_group_by_code[code]
                            for code in match_codes
                            if code and code in cbanner_mens_group_by_code
                        ),
                        None,
                    )
                image_path = archive_row.get("image_path") if archive_row else None
                image_matcher = self.image_matchers.get(IMAGE_BRAND_KEYS[brand_group])
                if image_path is None and image_matcher is not None:
                    image_path = next(
                        (
                            matched
                            for code in match_codes
                            if code
                            for matched in [image_matcher.find(code)]
                            if matched
                        ),
                        None,
                    )

                canonical = _gj_row_to_product_row(
                    row,
                    brand_group=brand_group,
                    archive_row=archive_row,
                    image_path=image_path,
                )
                if canonical is not None:
                    if cbanner_mens_group_name:
                        canonical["group_name"] = cbanner_mens_group_name
                    rows_by_brand[brand_group].append(canonical)

        return rows_by_brand
