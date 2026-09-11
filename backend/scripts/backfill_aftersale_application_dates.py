"""Backfill aftersale application dates used by rolling-window imports."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from config import load_settings


def main() -> int:
    settings = load_settings(require_database=True)
    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)

    with engine.begin() as connection:
        connection.execute(text("DROP VIEW IF EXISTS v_jst_aftersale_returns_normalized"))
        connection.execute(
            text(
                "ALTER TABLE jst_aftersale_returns "
                "ADD COLUMN IF NOT EXISTS application_date_value DATE"
            )
        )
        result = connection.execute(
            text(
                r"""
                UPDATE jst_aftersale_returns
                SET application_date_value = to_date(
                    split_part(
                        replace(
                            coalesce(
                                nullif(raw_payload ->> U&'\7533\8BF7\65E5\671F', ''),
                                nullif(raw_payload ->> U&'\767B\8BB0\65F6\95F4', '')
                            ),
                            '/', '-'
                        ),
                        ' ', 1
                    ),
                    'YYYY-MM-DD'
                )
                WHERE application_date_value IS NULL
                  AND coalesce(
                        nullif(raw_payload ->> U&'\7533\8BF7\65E5\671F', ''),
                        nullif(raw_payload ->> U&'\767B\8BB0\65F6\95F4', '')
                      ) ~ '^\d{4}[/-]\d{1,2}[/-]\d{1,2}'
                """
            )
        )
        print(f"[BACKFILL] updated={result.rowcount}", flush=True)

        connection.execute(text("DROP INDEX IF EXISTS idx_jst_aftersale_returns_business_date"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_jst_aftersale_returns_application_date "
                "ON jst_aftersale_returns (application_date_value)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_jst_aftersale_returns_business_date "
                "ON jst_aftersale_returns "
                "(COALESCE(application_date_value, order_date_value, order_time_value))"
            )
        )
        connection.execute(
            text(
                "CREATE VIEW v_jst_aftersale_returns_normalized AS "
                "SELECT source.*, "
                "COALESCE(source.application_date_value, source.order_date_value, "
                "source.order_time_value) AS business_date "
                "FROM jst_aftersale_returns AS source"
            )
        )

    print("[DONE] aftersale application-date backfill complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
