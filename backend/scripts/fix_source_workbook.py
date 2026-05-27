"""Update source_workbook from English keys to Chinese filenames.
Run: python -m scripts.fix_source_workbook
"""
from __future__ import annotations

from sqlalchemy import create_engine, text

from config import load_settings
from domain.sources import WORKBOOK_SPECS


def main() -> None:
    cfg = load_settings()

    key_to_filename: dict[str, str] = {}
    for spec in WORKBOOK_SPECS:
        try:
            path = spec.resolve_path(cfg.excel_root)
            key_to_filename[spec.workbook_key] = path.stem
        except FileNotFoundError:
            print(f"[WARN] 找不到文件，跳过: {spec.file_prefix}")

    assert cfg.database_url is not None
    engine = create_engine(cfg.database_url, future=True)

    brand_tables = [
        "cbanner_mens_products",
        "cbanner_womens_products",
        "yandou_products",
        "eblan_products",
    ]

    with engine.begin() as conn:
        for table_name in brand_tables:
            for key, filename in key_to_filename.items():
                result = conn.execute(
                    text(
                        f"UPDATE {table_name} SET source_workbook = :filename "
                        "WHERE source_workbook = :key"
                    ),
                    {"filename": filename, "key": key},
                )
                if result.rowcount:
                    print(f"[OK] {table_name}: {key} -> {filename} ({result.rowcount} 行)")

    print("Done.")


if __name__ == "__main__":
    main()
