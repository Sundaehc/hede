"""Create content-reference indexes for deduplicated fine-table snapshots."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from config import load_settings


def main() -> None:
    settings = load_settings(require_database=True)
    engine = create_engine(settings.database_url, future=True)
    table_names = sorted(
        table_name
        for table_name in inspect(engine).get_table_names()
        if table_name.startswith("fine_table_snapshot_refs_")
        and table_name.removeprefix("fine_table_snapshot_refs_").isdigit()
    )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        for table_name in table_names:
            for column_name in ("payload_id", "metrics_id"):
                index_name = f"idx_{table_name}_{column_name}"
                existing = connection.execute(
                    text(
                        "SELECT i.indisvalid "
                        "FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
                        "WHERE c.relname = :index_name"
                    ),
                    {"index_name": index_name},
                ).scalar_one_or_none()
                if existing is False:
                    connection.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))
                    print(f"dropped invalid {index_name}", flush=True)
                connection.execute(
                    text(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} "
                        f"ON {table_name} ({column_name})"
                    )
                )
                print(f"ensured {index_name}", flush=True)


if __name__ == "__main__":
    main()
