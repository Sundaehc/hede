from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "database" / "purchase-inbound-history-2026-10-27.sql"


def ensure_purchase_inbound_history_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text(SCHEMA_PATH.read_text(encoding="utf-8")))


def ensure_inbound_year(connection, year: int) -> None:
    if not 2000 <= year <= date.today().year + 1:
        raise ValueError(f"入库年份超出允许范围：{year}")
    connection.execute(text(
        f"CREATE TABLE IF NOT EXISTS public.jst_purchase_inbound_history_{year} "
        "PARTITION OF public.jst_purchase_inbound_history "
        f"FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')"
    ))


def refresh_inbound_age_reference(engine) -> None:
    with engine.begin() as connection:
        populated = connection.execute(text(
            "SELECT relispopulated FROM pg_class "
            "WHERE oid = 'public.mv_jst_purchase_inbound_age_reference'::regclass"
        )).scalar_one()
        concurrent = "CONCURRENTLY " if populated else ""
        connection.execute(text(
            f"REFRESH MATERIALIZED VIEW {concurrent}public.mv_jst_purchase_inbound_age_reference"
        ))
        connection.execute(text("ANALYZE public.jst_purchase_inbound_history"))
        connection.execute(text("ANALYZE public.mv_jst_purchase_inbound_age_reference"))


def query_inbound_history(
    connection, *, start_date: date, end_date: date,
    goods_code: str | None = None, style_color_code: str | None = None,
    warehouse: str | None = None, limit: int = 100,
) -> list[dict[str, object]]:
    if start_date >= end_date:
        raise ValueError("结束日期必须晚于开始日期，结束日期不包含当天")
    if not 1 <= limit <= 1000:
        raise ValueError("每次数量应为1至1000")
    conditions = ["history.inbound_date >= :start_date", "history.inbound_date < :end_date", "source.status = 'completed'"]
    parameters = {"start_date": start_date, "end_date": end_date, "limit": limit}
    for field, value in (("goods_code", goods_code), ("style_color_code", style_color_code), ("warehouse", warehouse)):
        if value:
            conditions.append(f"history.{field} = :{field}")
            parameters[field] = value.strip().upper() if field != "warehouse" else value.strip()
    result = connection.execute(text(
        "SELECT history.inbound_date, history.inbound_at, history.inbound_id, history.purchase_order_id, "
        "history.goods_code, history.style_color_code, history.original_sku, history.size, "
        "history.warehouse, history.supplier, history.quantity, history.amount, history.receipt_class, "
        "source.source_file, history.source_sheet, history.source_row_number "
        "FROM public.jst_purchase_inbound_history history "
        "JOIN public.jst_purchase_inbound_history_sources source ON source.id = history.source_id "
        "WHERE " + " AND ".join(conditions) +
        " ORDER BY history.inbound_date DESC, history.source_id DESC, "
        "history.source_sheet DESC, history.source_row_number DESC LIMIT :limit"
    ), parameters)
    return [dict(row) for row in result.mappings()]


def query_inbound_age_reference(
    connection, *, goods_code: str | None = None, style_color_code: str | None = None,
    warehouse: str | None = None,
) -> list[dict[str, object]]:
    if not goods_code and not style_color_code:
        raise ValueError("请指定商品编码或款式编码")
    conditions = []
    parameters = {}
    for field, value in (("goods_code", goods_code), ("style_color_code", style_color_code), ("warehouse", warehouse)):
        if value:
            conditions.append(f"{field} = :{field}")
            parameters[field] = value.strip().upper() if field != "warehouse" else value.strip()
    rows = connection.execute(text(
        "SELECT *, CURRENT_DATE - first_inbound_date AS first_receipt_age_days "
        "FROM public.mv_jst_purchase_inbound_age_reference WHERE " + " AND ".join(conditions) +
        " ORDER BY first_inbound_date, goods_code, warehouse"
    ), parameters)
    return [dict(row) for row in rows.mappings()]
