"""Move closed annual order-history partitions between hot and cold storage."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date

from sqlalchemy import create_engine, text

from config import load_settings
from domain.order_history_tiering import (
    cold_storage_capacity,
    list_order_history_partitions,
    lock_partition_for_tiering,
    move_partition_to_tablespace,
    partition_requires_tier_action,
    partition_row_count,
    protect_cold_partition,
    set_partition_comment,
    unprotect_partition,
    validate_cold_tablespace,
    validate_cold_storage_capacity,
    validate_distinct_physical_storage,
)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage PostgreSQL hot/cold storage for order history partitions"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reference-date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--keep-hot-years",
        type=int,
        default=int(os.getenv("ORDER_HISTORY_KEEP_HOT_YEARS", "2")),
    )
    parser.add_argument(
        "--cold-tablespace",
        default=os.getenv("ORDER_HISTORY_COLD_TABLESPACE", "").strip(),
    )
    parser.add_argument(
        "--hot-tablespace",
        default=os.getenv("ORDER_HISTORY_HOT_TABLESPACE", "pg_default").strip(),
    )
    parser.add_argument(
        "--partition",
        action="append",
        default=None,
        help="Limit the operation to one or more exact partition names",
    )
    parser.add_argument(
        "--restore-hot",
        action="store_true",
        help="Move selected cold partitions back to the hot tablespace",
    )
    parser.add_argument(
        "--allow-same-device",
        action="store_true",
        default=_env_flag("ORDER_HISTORY_ALLOW_SAME_PHYSICAL_DEVICE"),
        help="Allow logical hot/cold separation on different volumes of one disk",
    )
    return parser


def main() -> int:
    settings = load_settings(require_database=True)
    args = _parser().parse_args()
    if args.keep_hot_years < 1:
        raise ValueError("--keep-hot-years must be at least 1")
    if args.restore_hot and not args.partition:
        raise ValueError("--restore-hot requires at least one --partition")

    assert settings.database_url is not None
    engine = create_engine(settings.database_url, future=True)

    with engine.connect() as connection:
        partitions = list_order_history_partitions(
            connection,
            reference_date=args.reference_date,
            keep_hot_years=args.keep_hot_years,
        )
        selected_names = set(args.partition or ())
        if selected_names:
            known_names = {item.partition_name for item in partitions}
            unknown_names = sorted(selected_names - known_names)
            if unknown_names:
                raise ValueError(f"Unknown partitions: {', '.join(unknown_names)}")
            partitions = [
                item for item in partitions if item.partition_name in selected_names
            ]

        cold_location = None
        capacity = None
        physical_storage = None
        if args.cold_tablespace:
            cold_location = validate_cold_tablespace(connection, args.cold_tablespace)
            data_directory = str(
                connection.execute(text("SHOW data_directory")).scalar_one()
            )
            physical_storage = validate_distinct_physical_storage(
                data_directory,
                cold_location,
                allow_same_device=args.allow_same_device,
            )
            migration_bytes = sum(
                item.size_bytes
                for item in partitions
                if not args.restore_hot
                and item.desired_tier == "cold"
                and item.current_tablespace != args.cold_tablespace
            )
            capacity = cold_storage_capacity(cold_location, migration_bytes)
            if args.apply and migration_bytes:
                validate_cold_storage_capacity(cold_location, migration_bytes)
        elif args.apply and not args.restore_hot and any(
            item.desired_tier == "cold" for item in partitions
        ):
            raise ValueError(
                "ORDER_HISTORY_COLD_TABLESPACE or --cold-tablespace is required"
            )

    actions: list[dict[str, object]] = []
    if args.apply:
        for item in partitions:
            target_tier = "hot" if args.restore_hot else item.desired_tier
            target_tablespace = (
                args.hot_tablespace if target_tier == "hot" else args.cold_tablespace
            )
            if not target_tablespace:
                raise ValueError("A target tablespace is required")

            if not partition_requires_tier_action(
                item,
                target_tier=target_tier,
                target_tablespace=target_tablespace,
            ):
                continue

            moved = item.current_tablespace != target_tablespace
            with engine.begin() as connection:
                lock_partition_for_tiering(connection, item.partition_name)
                before_count = partition_row_count(connection, item.partition_name)
                if target_tier == "hot":
                    unprotect_partition(connection, item.partition_name)
                if moved:
                    indexes = move_partition_to_tablespace(
                        connection,
                        partition_name=item.partition_name,
                        tablespace_name=target_tablespace,
                    )
                else:
                    indexes = []
                if target_tier == "cold":
                    protect_cold_partition(connection, item.partition_name)
                after_count = partition_row_count(connection, item.partition_name)
                if after_count != before_count:
                    raise RuntimeError(
                        f"Row-count validation failed for {item.partition_name}: "
                        f"{before_count} -> {after_count}"
                    )
                set_partition_comment(
                    connection,
                    partition_name=item.partition_name,
                    tier=target_tier,
                    tablespace_name=target_tablespace,
                    reviewed_on=args.reference_date,
                )
                connection.execute(text(f"ANALYZE public.{item.partition_name}"))
            actions.append(
                {
                    "partition": item.partition_name,
                    "tier": target_tier,
                    "from_tablespace": item.current_tablespace,
                    "to_tablespace": target_tablespace,
                    "moved": moved,
                    "indexes_moved": indexes,
                    "row_count": after_count,
                }
            )

    report = {
        "reference_date": args.reference_date.isoformat(),
        "keep_hot_years": args.keep_hot_years,
        "apply": args.apply,
        "restore_hot": args.restore_hot,
        "cold_tablespace": args.cold_tablespace or None,
        "cold_tablespace_location": cold_location,
        "physical_storage": physical_storage,
        "same_physical_device": (
            physical_storage[0] == physical_storage[1]
            if physical_storage is not None
            else None
        ),
        "same_physical_device_allowed": args.allow_same_device,
        "cold_storage_capacity": asdict(capacity) if capacity else None,
        "partitions": [asdict(item) for item in partitions],
        "actions": actions,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
