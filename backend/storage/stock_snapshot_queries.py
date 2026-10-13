from __future__ import annotations

from datetime import date

from sqlalchemy import Date, select, text

from domain.jst_stock_snapshot_schema import JST_SIZE_STOCK_SNAPSHOT_TABLE


STOCK_SNAPSHOT_DATES_SQL = """
WITH RECURSIVE snapshot_dates AS (
    (SELECT snapshot_date FROM public.jst_size_stock_snapshots
     ORDER BY snapshot_date DESC LIMIT 1)
    UNION ALL
    SELECT earlier.snapshot_date
    FROM snapshot_dates AS previous
    CROSS JOIN LATERAL (
        SELECT snapshot_date FROM public.jst_size_stock_snapshots
        WHERE snapshot_date < previous.snapshot_date
        ORDER BY snapshot_date DESC LIMIT 1
    ) AS earlier
)
SELECT snapshot_date FROM snapshot_dates ORDER BY snapshot_date DESC
"""


def load_stock_snapshot_dates(connection) -> list[date]:
    if connection.dialect.name == "postgresql":
        statement = text(STOCK_SNAPSHOT_DATES_SQL).columns(snapshot_date=Date())
    else:
        statement = (
            select(JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date)
            .distinct()
            .order_by(JST_SIZE_STOCK_SNAPSHOT_TABLE.c.snapshot_date.desc())
        )
    return [value for value in connection.execute(statement).scalars() if isinstance(value, date)]
