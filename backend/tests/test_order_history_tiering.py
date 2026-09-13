from __future__ import annotations

from datetime import date
from collections import namedtuple

import pytest

from domain.order_history_tiering import (
    PartitionTier,
    checked_identifier,
    cold_storage_capacity,
    desired_partition_tier,
    partition_year,
    partition_requires_tier_action,
    sql_string_literal,
    validate_distinct_physical_storage,
    validate_cold_storage_capacity,
)


@pytest.mark.parametrize(
    ("partition_name", "expected"),
    [
        ("jst_monthly_orders_2024", 2024),
        ("jst_aftersale_returns_2026", 2026),
        ("dewu_orders_default", None),
    ],
)
def test_partition_year(partition_name: str, expected: int | None) -> None:
    assert partition_year(partition_name) == expected


def test_tier_policy_keeps_current_and_previous_year_hot() -> None:
    reference = date(2026, 9, 13)

    assert desired_partition_tier(2024, reference_date=reference, keep_hot_years=2) == "cold"
    assert desired_partition_tier(2025, reference_date=reference, keep_hot_years=2) == "hot"
    assert desired_partition_tier(2026, reference_date=reference, keep_hot_years=2) == "hot"
    assert desired_partition_tier(2027, reference_date=reference, keep_hot_years=2) == "hot"
    assert desired_partition_tier(None, reference_date=reference, keep_hot_years=2) == "hot"


def test_tier_policy_requires_at_least_one_hot_year() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        desired_partition_tier(2024, reference_date=date(2026, 9, 13), keep_hot_years=0)


def test_distinct_physical_storage_rejects_same_device() -> None:
    with pytest.raises(ValueError, match="same physical storage device"):
        validate_distinct_physical_storage(
            "D:/Postgresql/data",
            "E:/Postgresql/cold_archive",
            identity_resolver=lambda _path: "disk-0",
        )


def test_distinct_physical_storage_accepts_different_devices() -> None:
    identities = {
        "D:/Postgresql/data": "disk-0",
        "F:/Postgresql/cold_archive": "disk-1",
    }
    assert validate_distinct_physical_storage(
        "D:/Postgresql/data",
        "F:/Postgresql/cold_archive",
        identity_resolver=identities.__getitem__,
    ) == ("disk-0", "disk-1")


def test_distinct_physical_storage_allows_explicit_same_device_override() -> None:
    assert validate_distinct_physical_storage(
        "D:/Postgresql/data",
        "E:/Postgresql/cold_archive",
        allow_same_device=True,
        identity_resolver=lambda _path: "disk-0",
    ) == ("disk-0", "disk-0")


def test_cold_storage_capacity_reserves_at_least_five_gib() -> None:
    usage = namedtuple("usage", "total used free")
    gib = 1024**3

    result = cold_storage_capacity(
        "F:/Postgresql/cold_archive",
        10 * gib,
        disk_usage_resolver=lambda _path: usage(100 * gib, 70 * gib, 30 * gib),
    )

    assert result.reserve_bytes == 5 * gib
    assert result.required_free_bytes == 15 * gib
    assert result.sufficient is True


def test_cold_storage_capacity_uses_fifteen_percent_for_large_migration() -> None:
    usage = namedtuple("usage", "total used free")
    gib = 1024**3

    result = cold_storage_capacity(
        "F:/Postgresql/cold_archive",
        100 * gib,
        disk_usage_resolver=lambda _path: usage(200 * gib, 60 * gib, 140 * gib),
    )

    assert result.reserve_bytes == 15 * gib
    assert result.required_free_bytes == 115 * gib


def test_validate_cold_storage_capacity_rejects_insufficient_space() -> None:
    usage = namedtuple("usage", "total used free")
    gib = 1024**3

    with pytest.raises(ValueError, match="insufficient free space"):
        validate_cold_storage_capacity(
            "F:/Postgresql/cold_archive",
            10 * gib,
            disk_usage_resolver=lambda _path: usage(100 * gib, 88 * gib, 12 * gib),
        )


@pytest.mark.parametrize("value", ["orders; DROP TABLE users", "MixedCase", "a-b"])
def test_checked_identifier_rejects_unsafe_names(value: str) -> None:
    with pytest.raises(ValueError, match="Unsupported PostgreSQL identifier"):
        checked_identifier(value)


def test_sql_string_literal_escapes_single_quotes() -> None:
    assert sql_string_literal("cold owner's tier") == "'cold owner''s tier'"


def _partition(*, tablespace: str, protected: bool) -> PartitionTier:
    return PartitionTier(
        parent_name="jst_monthly_orders",
        partition_name="jst_monthly_orders_2024",
        partition_year=2024,
        current_tablespace=tablespace,
        tablespace_location="",
        size_bytes=1,
        desired_tier="cold",
        cold_write_protected=protected,
    )


def test_tier_action_skips_partition_already_cold_and_protected() -> None:
    assert not partition_requires_tier_action(
        _partition(tablespace="hede_cold_archive", protected=True),
        target_tier="cold",
        target_tablespace="hede_cold_archive",
    )


def test_tier_action_repairs_missing_cold_write_protection() -> None:
    assert partition_requires_tier_action(
        _partition(tablespace="hede_cold_archive", protected=False),
        target_tier="cold",
        target_tablespace="hede_cold_archive",
    )
