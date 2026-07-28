from datetime import date

import pytest

from domain.fine_table_snapshot_schema import fine_table_snapshot_row_table_for_date
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
