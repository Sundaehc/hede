from __future__ import annotations

from dataclasses import dataclass

from config import Settings
from domain.sources import IMAGE_BRAND_KEYS, WORKBOOK_SPECS
from fileio.excel_reader import read_workbook_rows
from fileio.image_matcher import ImageMatcher
from storage.db import Database
from transform.rows import build_canonical_row


@dataclass
class ImportSummary:
    brand_group: str
    extracted_rows: int = 0
    loaded_rows: int = 0
    skipped_rows: int = 0
    missing_images: int = 0


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
                    if image_path is None:
                        summaries[spec.brand_group].missing_images += 1
                    rows_by_brand[spec.brand_group].append(canonical)

        if not dry_run:
            self.database.create_tables()
            for brand_group, rows in rows_by_brand.items():
                if mode == "sync":
                    summaries[brand_group].loaded_rows = self.database.upsert_brand_rows(brand_group, rows)
                else:
                    summaries[brand_group].loaded_rows = self.database.replace_brand_rows(brand_group, rows)
        else:
            for brand_group, rows in rows_by_brand.items():
                summaries[brand_group].loaded_rows = len(rows)

        return summaries
