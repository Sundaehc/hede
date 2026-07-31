from datetime import date

import pytest
from sqlalchemy import create_engine, insert, select

from domain.fine_table_snapshot_schema import (
    FINE_TABLE_SNAPSHOT_METRICS_TABLE,
    FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE,
    fine_table_snapshot_ref_table_for_date,
    fine_table_snapshot_row_table_for_date,
)
from storage.fine_table_snapshot_dedup import split_snapshot_payload
from storage.fine_table_snapshot_dedup import (
    cleanup_orphaned_snapshot_content,
    load_optimized_snapshot_rows,
    write_optimized_snapshot_rows,
)
from domain.legacy_partitioning import LegacyPartitionTarget
from domain.master_data_schema import (
    MASTER_DATA_ALIASES_TABLE,
    MASTER_DATA_ENTITIES_TABLE,
    PRODUCT_CODE_MAPPINGS_TABLE,
)


def test_fine_snapshot_rows_include_the_partition_key():
    table = fine_table_snapshot_row_table_for_date(date(2026, 7, 27))

    assert "snapshot_date" in table.c
    assert table.c.snapshot_date.nullable is False


def test_fine_snapshot_dedup_tables_keep_payloads_and_references_separate():
    ref_table = fine_table_snapshot_ref_table_for_date(date(2026, 7, 27))

    assert {"payload_id", "metrics_id", "batch_id", "row_index"} <= set(ref_table.c.keys())
    assert {
        "idx_fine_table_snapshot_refs_2026_sku_trgm",
        "idx_fine_table_snapshot_refs_2026_original_sku_trgm",
        "idx_fine_table_snapshot_refs_2026_payload_id",
        "idx_fine_table_snapshot_refs_2026_metrics_id",
    } <= {index.name for index in ref_table.indexes}
    assert {"brand", "content_hash", "payload"} <= set(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.keys())
    assert {"brand", "content_hash", "payload"} <= set(FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.keys())


def test_split_snapshot_payload_preserves_complete_row_after_merge():
    stable, metrics = split_snapshot_payload({
        "sku": "A-1",
        "factory_name": "工厂A",
        "stock_qty": 12,
        "daily_sales": [{"date": "2026-07-30", "quantity": 2}],
    })

    assert stable == {"sku": "A-1", "factory_name": "工厂A"}
    assert metrics == {
        "stock_qty": 12,
        "daily_sales": [{"date": "2026-07-30", "quantity": 2}],
    }


def test_optimized_snapshot_reuses_stable_payload_and_preserves_daily_metrics(
    test_database_url: str,
    recreate_tables,
):
    engine = create_engine(test_database_url, future=True)
    snapshot_date = date(2026, 7, 30)
    with engine.begin() as connection:
        first_batch_id = connection.execute(
            insert(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .values(brand="cbanner_mens", snapshot_date=snapshot_date, total_rows=1)
            .returning(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id)
        ).scalar_one()
        second_batch_id = connection.execute(
            insert(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .values(brand="cbanner_mens", snapshot_date=date(2026, 7, 31), total_rows=1)
            .returning(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id)
        ).scalar_one()

    first_item = {"sku": "A-1", "factory_name": "工厂A", "stock_qty": 12}
    second_item = {**first_item, "stock_qty": 8}
    write_optimized_snapshot_rows(
        engine,
        brand="cbanner_mens",
        snapshot_date=snapshot_date,
        batch_id=int(first_batch_id),
        payloads=[first_item],
    )
    write_optimized_snapshot_rows(
        engine,
        brand="cbanner_mens",
        snapshot_date=date(2026, 7, 31),
        batch_id=int(second_batch_id),
        payloads=[second_item],
    )

    with engine.connect() as connection:
        assert len(connection.execute(select(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.id)).all()) == 1
        assert len(connection.execute(select(FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.id)).all()) == 2

    rows, total = load_optimized_snapshot_rows(
        engine,
        snapshot_date,
        int(first_batch_id),
        conditions=[],
        page=1,
        page_size=20,
    )
    assert total == 1
    assert rows == [first_item]


def test_snapshot_orphan_cleanup_keeps_referenced_content(
    test_database_url: str,
    recreate_tables,
):
    engine = create_engine(test_database_url, future=True)
    snapshot_date = date(2026, 7, 30)
    with engine.begin() as connection:
        batch_id = connection.execute(
            insert(FINE_TABLE_SNAPSHOT_BATCH_TABLE)
            .values(brand="cbanner_mens", snapshot_date=snapshot_date, total_rows=1)
            .returning(FINE_TABLE_SNAPSHOT_BATCH_TABLE.c.id)
        ).scalar_one()
    write_optimized_snapshot_rows(
        engine,
        brand="cbanner_mens",
        snapshot_date=snapshot_date,
        batch_id=int(batch_id),
        payloads=[{"sku": "A-1", "stock_qty": 12}],
    )
    with engine.begin() as connection:
        connection.execute(
            insert(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE).values(
                brand="cbanner_mens",
                content_hash="orphan-payload",
                payload={"sku": "ORPHAN"},
            )
        )
        connection.execute(
            insert(FINE_TABLE_SNAPSHOT_METRICS_TABLE).values(
                brand="cbanner_mens",
                content_hash="orphan-metrics",
                payload={"stock_qty": 0},
            )
        )

    preview = cleanup_orphaned_snapshot_content(engine)
    assert preview["payload_candidates"] == 1
    assert preview["metrics_candidates"] == 1
    assert preview["payload_deleted"] == 0

    result = cleanup_orphaned_snapshot_content(engine, execute=True)
    assert result["payload_deleted"] == 1
    assert result["metrics_deleted"] == 1
    with engine.connect() as connection:
        assert connection.execute(select(FINE_TABLE_SNAPSHOT_PAYLOADS_TABLE.c.id)).all()
        assert connection.execute(select(FINE_TABLE_SNAPSHOT_METRICS_TABLE.c.id)).all()


def test_master_data_tables_keep_canonical_and_raw_values():
    assert {"entity_type", "canonical_name", "raw_payload"} <= set(MASTER_DATA_ENTITIES_TABLE.c.keys())
    assert {"entity_id", "alias_name", "normalized_name", "source_system"} <= set(MASTER_DATA_ALIASES_TABLE.c.keys())
    assert {"brand", "code_type", "code_value", "canonical_product_code"} <= set(PRODUCT_CODE_MAPPINGS_TABLE.c.keys())
    constraints = [
        constraint
        for constraint in PRODUCT_CODE_MAPPINGS_TABLE.constraints
        if getattr(constraint, "name", None) == "uq_product_code_mappings_brand_type_value_canonical"
    ]
    assert len(constraints) == 1


def test_partition_target_rejects_unsafe_identifiers_and_bounds():
    with pytest.raises(ValueError):
        LegacyPartitionTarget(
            parent_name="fine_table_snapshot_rows; drop table x",
            child_name="fine_table_snapshot_rows_2026",
            partition_key="snapshot_date",
            lower_bound="2026-01-01",
            upper_bound="2027-01-01",
        )

    with pytest.raises(ValueError):
        LegacyPartitionTarget(
            parent_name="fine_table_snapshot_rows",
            child_name="fine_table_snapshot_rows_2026",
            partition_key="snapshot_date",
            lower_bound="2026-invalid",
            upper_bound="2027-01-01",
        )
