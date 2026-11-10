"""Preview or apply readable brand product archive names in one transaction."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, text

from config import load_settings
from storage.product_archive_table_names import archive_table_rename_plan, rename_product_archive_tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Apply renames; default is read-only preview")
    parser.add_argument("--downgrade", action="store_true", help="Restore manual_product_archive_<ID> names")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(load_settings().database_url, pool_size=1, max_overflow=0,
                           connect_args={"connect_timeout": 10})
    report = {"execute": args.execute, "downgrade": args.downgrade}
    try:
        with engine.begin() as connection:
            if not args.execute:
                connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            plan = archive_table_rename_plan(connection, downgrade=args.downgrade)
            quote = connection.dialect.identifier_preparer.quote_identifier
            before = {}
            for item in plan:
                before[item["brand_id"]] = dict(connection.execute(text(
                    f"SELECT count(*) AS rows, min(id) AS min_id, max(id) AS max_id FROM {quote(item['old'])}"
                )).mappings().one())
            report["plan"] = plan
            if args.execute:
                applied = rename_product_archive_tables(connection, downgrade=args.downgrade)
                if applied != plan:
                    raise ValueError("Brand configuration changed during migration; retry the preview")
                for item in applied:
                    after = dict(connection.execute(text(
                        f"SELECT count(*) AS rows, min(id) AS min_id, max(id) AS max_id FROM {quote(item['new'])}"
                    )).mappings().one())
                    if after != before[item["brand_id"]]:
                        raise ValueError("Product archive changed during migration; rolling back")
            report["archives"] = before
    finally:
        engine.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
