"""Rolling fine-table quantities from the imported VIP daily sales facts."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import Date, Integer, Text, case, column, func, inspect, or_, select, table
from sqlalchemy.engine import Connection


WINDOW_DAYS = (1, 2, 3, 4, 5, 6, 7, 14, 15, 30)
SKU_BATCH_SIZE = 500
VIP_SALES_FACTS = table(
    "vip_daily_sales",
    column("sales_date", Date),
    column("goods_code", Text),
    column("brand_name", Text),
    column("sales_quantity", Integer),
)
BRAND_MARKERS = {
    "cbanner_mens": ("千百度", "C.banner", "CBANNER"),
    "cbanner_womens": ("千百度", "C.banner", "CBANNER"),
    "yandou": ("烟斗", "TRUMPPIPE", "yandou"),
    "eblan": ("伊伴", "EBLAN"),
}


def load_vip_sales_windows(
    connection: Connection, skus: Iterable[str | None], *, brand: str,
) -> tuple[date | None, dict[str, dict[int, int]]]:
    """Sum all size/goods IDs by exact archive SKU, using one shared end day.

    The parent relation includes all year partitions, including cross-year
    windows. Query it once per batch, never union it with its children. The
    latest fact date is independent of page/search results. This read path
    never creates tables or substitutes Compass quantities for missing facts.
    """
    markers = BRAND_MARKERS[brand]
    codes = sorted({str(sku).strip() for sku in skus if str(sku or "").strip()})
    if not codes or not inspect(connection).has_table(VIP_SALES_FACTS.name):
        return None, {}
    facts = VIP_SALES_FACTS
    end_date = connection.execute(select(func.max(facts.c.sales_date))).scalar()
    if not isinstance(end_date, date):
        return None, {}
    start_date = end_date - timedelta(days=29)
    totals = {}
    # Exact SKU matches may occur in different brands. An explicit foreign
    # brand cannot contribute; older blank brand labels remain usable.
    brand_condition = or_(
        facts.c.brand_name.is_(None), func.trim(facts.c.brand_name) == "",
        *(facts.c.brand_name.ilike(f"%{marker}%") for marker in markers),
    )
    for start in range(0, len(codes), SKU_BATCH_SIZE):
        rows = connection.execute(select(
            facts.c.goods_code,
            *(func.coalesce(func.sum(case(
                (facts.c.sales_date >= end_date - timedelta(days=days - 1),
                 func.coalesce(facts.c.sales_quantity, 0)), else_=0,
            )), 0).label(f"days_{days}") for days in WINDOW_DAYS),
        ).where(
            facts.c.goods_code.in_(codes[start:start + SKU_BATCH_SIZE]),
            facts.c.sales_date.between(start_date, end_date), brand_condition,
        ).group_by(facts.c.goods_code)).mappings()
        for row in rows:
            totals[row["goods_code"]] = {days: int(row[f"days_{days}"] or 0) for days in WINDOW_DAYS}
    return end_date, totals


def load_yandou_vip_sales_windows(
    connection: Connection, skus: Iterable[str | None],
) -> tuple[date | None, dict[str, dict[int, int]]]:
    """Compatibility entry for existing Yandou verification scripts."""
    return load_vip_sales_windows(connection, skus, brand="yandou")
