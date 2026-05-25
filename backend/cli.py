from __future__ import annotations

import argparse
from collections.abc import Sequence

from config import load_settings
from pipeline.import_pipeline import ImportPipeline



def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import product Excel archives into PostgreSQL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("dry-run", help="Read and summarize source data without writing to PostgreSQL")
    subparsers.add_parser("import", help="Import source data into PostgreSQL")
    subparsers.add_parser("sync", help="Upsert source data into PostgreSQL without deleting missing rows")
    return parser



def _print_summary(command: str, summaries) -> None:
    print(f"Mode: {command}")
    for brand_group, summary in summaries.items():
        print(
            f"{brand_group}: extracted={summary.extracted_rows}, "
            f"loaded={summary.loaded_rows}, skipped={summary.skipped_rows}, "
            f"missing_images={summary.missing_images}"
        )



def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    settings = load_settings(require_database=args.command in ("import", "sync"))
    pipeline = ImportPipeline(settings)
    summaries = pipeline.run(
        dry_run=args.command == "dry-run",
        mode="sync" if args.command == "sync" else "replace",
    )
    _print_summary(args.command, summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
