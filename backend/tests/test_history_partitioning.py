from __future__ import annotations

from sqlalchemy import create_engine

from domain.history_partitioning import ensure_annual_partitions


def test_ensure_annual_partitions_is_noop_outside_postgresql() -> None:
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        created = ensure_annual_partitions(
            connection,
            "dewu_orders",
            {2026},
        )

    assert created == []
