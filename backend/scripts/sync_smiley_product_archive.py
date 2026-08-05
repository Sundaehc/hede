from __future__ import annotations

from datetime import date

from config import load_settings
from pipeline.import_pipeline import ImportPipeline


def main() -> None:
    """Populate or refresh only the editable Smiley product archive."""
    pipeline = ImportPipeline(load_settings())
    rows_by_brand = pipeline._build_product_rows_from_gj({"smiley": {}})
    rows = rows_by_brand["smiley"]
    pipeline.database.create_tables()
    pipeline.database.sync_brand_rows(
        "smiley",
        rows,
        refresh_launch_year=date.today().year,
    )
    print(f"Smiley product archive synced from {len(rows)} source rows")


if __name__ == "__main__":
    main()
