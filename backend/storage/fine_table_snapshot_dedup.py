from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import and_, delete, exists, func, insert, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_METRICS_TABLE,
    FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE,
    ensure_fine_table_snapshot_ref_table,
    fine_table_snapshot_ref_table_exists,
    fine_table_snapshot_ref_table_for_date,
    list_fine_table_snapshot_ref_tables,
)


DYNAMIC_KEYS = frozenset({
    "latest_purchase_price",
    "final_price",
    "vip_price",
    "market_price",
    "price_band",
    "activity_profit",
    "margin_rate",
    "discount_rate",
    "vip_1d_sales",
    "vip_3d_sales",
    "vip_7d_sales",
    "vip_15d_sales",
    "vip_30d_sales",
    "vip_3d_uv",
    "vip_7d_uv",
    "vip_30d_uv",
    "vip_3d_ctr",
    "vip_7d_ctr",
    "vip_30d_ctr",
    "vip_3d_conversion",
    "vip_7d_conversion",
    "vip_30d_conversion",
    "vip_3d_sales_change_rate",
    "vip_3d_uv_change_rate",
    "vip_3d_ctr_change_rate",
    "vip_3d_conversion_change_rate",
    "vip_7d_sales_change_rate",
    "vip_7d_uv_change_rate",
    "vip_7d_ctr_change_rate",
    "vip_7d_conversion_change_rate",
    "vip_30d_reject_count",
    "vip_30d_reject_rate",
    "vip_daily_average_sales",
    "other_3d_sales",
    "other_7d_sales",
    "other_15d_sales",
    "other_30d_sales",
    "original_other_3d_sales",
    "original_other_7d_sales",
    "original_all_7d_sales",
    "original_other_15d_sales",
    "original_other_30d_sales",
    "shop_30d_sales",
    "stock_qty",
    "original_stock_qty",
    "size_stock",
    "inbound_qty",
    "defect_stock",
    "original_defect_stock",
    "original_inbound_qty",
    "original_order_in_transit_stock",
    "original_defect_in_transit_stock",
    "off_shelf_stock",
    "order_occupy_stock",
    "defect_in_transit_stock",
    "purchase_diff",
    "projected_15d_stock",
    "daily_sales",
    "main_style",
    "goods_id",
    "p_spu",
    "style_code",
    "category_l3",
    "goods_status",
    "status_key",
    "sales_tag",
    "goods_tag",
    "risk",
})


def _content_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def split_snapshot_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    stable = {key: value for key, value in payload.items() if key not in DYNAMIC_KEYS}
    metrics = {key: value for key, value in payload.items() if key in DYNAMIC_KEYS}
    return stable, metrics


def optimized_snapshot_available(engine, snapshot_date, batch_id: int) -> bool:
    if not fine_table_snapshot_ref_table_exists(engine, snapshot_date):
        return False
    table = fine_table_snapshot_ref_table_for_date(snapshot_date)
    with engine.connect() as connection:
        return connection.execute(
            select(table.c.id).where(table.c.batch_id == batch_id).limit(1)
        ).first() is not None


def write_optimized_snapshot_rows(
    bind: Engine | Connection,
    *,
    brand: str,
    snapshot_date,
    batch_id: int,
    payloads: list[dict[str, Any]],
) -> int:
    FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.create(bind, checkfirst=True)
    FINE_TABLE_SNAPSHOT_METRICS_TABLE.create(bind, checkfirst=True)
    ref_table = ensure_fine_table_snapshot_ref_table(bind, snapshot_date)
    if isinstance(bind, Connection):
        return _write_optimized_snapshot_rows(
            bind,
            ref_table=ref_table,
            brand=brand,
            snapshot_date=snapshot_date,
            batch_id=batch_id,
            payloads=payloads,
        )

    with bind.begin() as connection:
        return _write_optimized_snapshot_rows(
            connection,
            ref_table=ref_table,
            brand=brand,
            snapshot_date=snapshot_date,
            batch_id=batch_id,
            payloads=payloads,
        )


def _write_optimized_snapshot_rows(
    connection: Connection,
    *,
    ref_table,
    brand: str,
    snapshot_date,
    batch_id: int,
    payloads: list[dict[str, Any]],
) -> int:
    stable_records: dict[str, dict[str, Any]] = {}
    metric_records: dict[str, dict[str, Any]] = {}
    split_rows: list[tuple[dict[str, Any], dict[str, Any], str, str]] = []
    for payload in payloads:
        stable, metrics = split_snapshot_payload(payload)
        stable_hash = _content_hash(stable)
        metric_hash = _content_hash(metrics)
        stable_records.setdefault(stable_hash, {"brand": brand, "content_hash": stable_hash, "payload": stable})
        metric_records.setdefault(metric_hash, {"brand": brand, "content_hash": metric_hash, "payload": metrics})
        split_rows.append((payload, stable, stable_hash, metric_hash))

    connection.execute(delete(ref_table).where(ref_table.c.batch_id == batch_id))
    for table, records in (
        (FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE, stable_records),
        (FINE_TABLE_SNAPSHOT_METRICS_TABLE, metric_records),
    ):
        values = list(records.values())
        for start in range(0, len(values), 1000):
            chunk = values[start:start + 1000]
            if chunk:
                connection.execute(
                    pg_insert(table).values(chunk).on_conflict_do_nothing(
                        constraint=f"uq_{table.name}_brand_hash"
                    )
                )

    stable_ids: dict[str, int] = {}
    metric_ids: dict[str, int] = {}
    for table, records, target in (
        (FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE, stable_records, stable_ids),
        (FINE_TABLE_SNAPSHOT_METRICS_TABLE, metric_records, metric_ids),
    ):
        hashes = list(records)
        for start in range(0, len(hashes), 1000):
            rows = connection.execute(
                select(table.c.id, table.c.content_hash)
                .where(table.c.brand == brand)
                .where(table.c.content_hash.in_(hashes[start:start + 1000]))
            ).mappings()
            target.update({str(row["content_hash"]): int(row["id"]) for row in rows})

    refs = [
        {
            "batch_id": batch_id,
            "snapshot_date": snapshot_date,
            "sku": str(payload.get("sku") or "").strip() or None,
            "original_sku": str(payload.get("original_sku") or "").strip() or None,
            "row_index": index,
            "payload_id": stable_ids[stable_hash],
            "metrics_id": metric_ids[metric_hash],
        }
        for index, (payload, _stable, stable_hash, metric_hash) in enumerate(split_rows, start=1)
    ]
    for start in range(0, len(refs), 1000):
        connection.execute(insert(ref_table), refs[start:start + 1000])
    return len(refs)


def load_optimized_snapshot_rows(engine, snapshot_date, batch_id: int, *, conditions: list[Any], page: int, page_size: int):
    ref_table = fine_table_snapshot_ref_table_for_date(snapshot_date)
    statement = (
        select(
            ref_table.c.payload_id,
            ref_table.c.metrics_id,
            FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.payload.label("stable_payload"),
            FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.payload.label("metrics_payload"),
        )
        .select_from(
            ref_table
            .join(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE, FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.id == ref_table.c.payload_id)
            .join(FINE_TABLE_SNAPSHOT_METRICS_TABLE, FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.id == ref_table.c.metrics_id)
        )
        .where(ref_table.c.batch_id == batch_id)
        .where(*conditions)
        .order_by(ref_table.c.row_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_statement = select(ref_table.c.id).select_from(ref_table).where(ref_table.c.batch_id == batch_id).where(*conditions)
    with engine.connect() as connection:
        rows = [
            {**(row["stable_payload"] or {}), **(row["metrics_payload"] or {})}
            for row in connection.execute(statement).mappings()
        ]
        total = connection.execute(select(func.count()).select_from(count_statement.subquery())).scalar_one()
    return rows, int(total)


def load_all_optimized_snapshot_rows(engine, snapshot_date, batch_id: int) -> list[dict[str, Any]]:
    rows, _total = load_optimized_snapshot_rows(
        engine,
        snapshot_date,
        batch_id,
        conditions=[],
        page=1,
        page_size=1_000_000,
    )
    return rows


def delete_optimized_snapshot_rows_for_skus(engine, snapshot_date, skus: list[str]) -> int:
    if not skus or not fine_table_snapshot_ref_table_exists(engine, snapshot_date):
        return 0
    ref_table = fine_table_snapshot_ref_table_for_date(snapshot_date)
    with engine.begin() as connection:
        result = connection.execute(
            delete(ref_table).where(
                or_(ref_table.c.sku.in_(skus), ref_table.c.original_sku.in_(skus))
            )
        )
    return int(result.rowcount or 0)


def cleanup_orphaned_snapshot_content(engine: Engine, *, execute: bool = False) -> dict[str, Any]:
    ref_tables = list_fine_table_snapshot_ref_tables(engine)
    if not ref_tables:
        return {
            "executed": execute,
            "ref_tables": [],
            "payload_candidates": 0,
            "payload_deleted": 0,
            "metrics_candidates": 0,
            "metrics_deleted": 0,
        }

    payload_candidates = select(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.id).where(
        and_(
            *(
                ~exists(
                    select(1).select_from(table).where(
                        table.c.payload_id == FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.id
                    )
                )
                for table in ref_tables
            )
        )
    )
    metrics_candidates = select(FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.id).where(
        and_(
            *(
                ~exists(
                    select(1).select_from(table).where(
                        table.c.metrics_id == FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.id
                    )
                )
                for table in ref_tables
            )
        )
    )

    with engine.begin() as connection:
        payload_count = int(
            connection.execute(select(func.count()).select_from(payload_candidates.subquery())).scalar_one()
        )
        metrics_count = int(
            connection.execute(select(func.count()).select_from(metrics_candidates.subquery())).scalar_one()
        )
        if execute:
            connection.execute(
                delete(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE).where(
                    FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.id.in_(payload_candidates)
                )
            )
            connection.execute(
                delete(FINE_TABLE_SNAPSHOT_METRICS_TABLE).where(
                    FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.id.in_(metrics_candidates)
                )
            )

    return {
        "executed": execute,
        "ref_tables": [table.name for table in ref_tables],
        "payload_candidates": payload_count,
        "payload_deleted": payload_count if execute else 0,
        "metrics_candidates": metrics_count,
        "metrics_deleted": metrics_count if execute else 0,
    }
