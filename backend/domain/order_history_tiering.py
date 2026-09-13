from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection


ORDER_HISTORY_PARENTS = (
    "jst_monthly_orders",
    "jst_aftersale_returns",
    "dewu_orders",
)
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class PartitionTier:
    parent_name: str
    partition_name: str
    partition_year: int | None
    current_tablespace: str
    tablespace_location: str
    size_bytes: int
    desired_tier: str
    cold_write_protected: bool


@dataclass(frozen=True)
class ColdStorageCapacity:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    migration_bytes: int
    reserve_bytes: int
    required_free_bytes: int
    sufficient: bool


def checked_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsupported PostgreSQL identifier: {value!r}")
    return value


def sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def partition_year(partition_name: str) -> int | None:
    suffix = partition_name.rsplit("_", 1)[-1]
    return int(suffix) if len(suffix) == 4 and suffix.isdigit() else None


def desired_partition_tier(
    partition_year_value: int | None,
    *,
    reference_date: date,
    keep_hot_years: int,
) -> str:
    if keep_hot_years < 1:
        raise ValueError("keep_hot_years must be at least 1")
    if partition_year_value is None:
        return "hot"
    oldest_hot_year = reference_date.year - keep_hot_years + 1
    return "cold" if partition_year_value < oldest_hot_year else "hot"


def partition_requires_tier_action(
    partition: PartitionTier,
    *,
    target_tier: str,
    target_tablespace: str,
) -> bool:
    if target_tier not in {"hot", "cold"}:
        raise ValueError(f"Unsupported storage tier: {target_tier}")
    expected_protection = target_tier == "cold"
    return (
        partition.current_tablespace != target_tablespace
        or partition.cold_write_protected != expected_protection
    )


def tablespace_location(connection: Connection, tablespace_name: str) -> str:
    checked_identifier(tablespace_name)
    row = connection.execute(
        text(
            """
            SELECT pg_tablespace_location(oid)
            FROM pg_tablespace
            WHERE spcname = :tablespace_name
            """
        ),
        {"tablespace_name": tablespace_name},
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"PostgreSQL tablespace does not exist: {tablespace_name}")
    return str(row or "")


def validate_cold_tablespace(
    connection: Connection,
    cold_tablespace: str,
) -> str:
    if cold_tablespace in {"pg_default", "pg_global"}:
        raise ValueError("Cold archive must use a dedicated PostgreSQL tablespace")
    location = tablespace_location(connection, cold_tablespace)
    if not location:
        raise ValueError("Cold archive tablespace must have an external location")

    data_directory = str(connection.execute(text("SHOW data_directory")).scalar_one())
    normalized_location = location.replace("\\", "/").rstrip("/").casefold()
    normalized_data = data_directory.replace("\\", "/").rstrip("/").casefold()
    if normalized_location == normalized_data or normalized_location.startswith(
        normalized_data + "/"
    ):
        raise ValueError(
            "Cold archive tablespace must be outside the PostgreSQL data directory"
        )
    return location


def _windows_storage_device_number(path: str) -> int:
    import ctypes
    from ctypes import wintypes

    drive = Path(path).drive.rstrip("\\/")
    if not re.fullmatch(r"[A-Za-z]:", drive):
        raise ValueError(f"Cold archive must use a local Windows drive: {path}")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.DeviceIoControl.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    kernel32.DeviceIoControl.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        f"\\\\.\\{drive}",
        0,
        0x00000001 | 0x00000002,
        None,
        3,
        0,
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), f"Cannot inspect storage device: {drive}")

    class StorageDeviceNumber(ctypes.Structure):
        _fields_ = [
            ("device_type", wintypes.DWORD),
            ("device_number", wintypes.DWORD),
            ("partition_number", wintypes.DWORD),
        ]

    try:
        result = StorageDeviceNumber()
        returned = wintypes.DWORD()
        success = kernel32.DeviceIoControl(
            handle,
            0x002D1080,
            None,
            0,
            ctypes.byref(result),
            ctypes.sizeof(result),
            ctypes.byref(returned),
            None,
        )
        if not success:
            raise OSError(
                ctypes.get_last_error(),
                f"Cannot inspect storage device: {drive}",
            )
        return int(result.device_number)
    finally:
        kernel32.CloseHandle(handle)


def storage_device_identity(path: str) -> str:
    if sys.platform == "win32":
        return f"windows-disk-{_windows_storage_device_number(path)}"
    return f"posix-device-{os.stat(path).st_dev}"


def validate_distinct_physical_storage(
    data_directory: str,
    cold_location: str,
    *,
    allow_same_device: bool = False,
    identity_resolver: Callable[[str], str] = storage_device_identity,
) -> tuple[str, str]:
    hot_identity = identity_resolver(data_directory)
    cold_identity = identity_resolver(cold_location)
    if hot_identity == cold_identity and not allow_same_device:
        raise ValueError(
            "Cold archive tablespace is on the same physical storage device "
            f"as PostgreSQL data: {hot_identity}; set "
            "ORDER_HISTORY_ALLOW_SAME_PHYSICAL_DEVICE=true only when this "
            "reduced isolation is explicitly accepted"
        )
    return hot_identity, cold_identity


def cold_storage_capacity(
    cold_location: str,
    migration_bytes: int,
    *,
    disk_usage_resolver: Callable[[str], object] = shutil.disk_usage,
) -> ColdStorageCapacity:
    if migration_bytes < 0:
        raise ValueError("migration_bytes cannot be negative")
    usage = disk_usage_resolver(cold_location)
    total = int(getattr(usage, "total"))
    used = int(getattr(usage, "used"))
    free = int(getattr(usage, "free"))
    reserve = max(5 * 1024**3, (migration_bytes * 15 + 99) // 100)
    required = migration_bytes + reserve
    return ColdStorageCapacity(
        total_bytes=total,
        used_bytes=used,
        free_bytes=free,
        migration_bytes=migration_bytes,
        reserve_bytes=reserve,
        required_free_bytes=required,
        sufficient=free >= required,
    )


def validate_cold_storage_capacity(
    cold_location: str,
    migration_bytes: int,
    *,
    disk_usage_resolver: Callable[[str], object] = shutil.disk_usage,
) -> ColdStorageCapacity:
    capacity = cold_storage_capacity(
        cold_location,
        migration_bytes,
        disk_usage_resolver=disk_usage_resolver,
    )
    if not capacity.sufficient:
        gib = 1024**3
        raise ValueError(
            "Cold archive storage has insufficient free space: "
            f"free={capacity.free_bytes / gib:.2f} GiB, "
            f"required={capacity.required_free_bytes / gib:.2f} GiB "
            f"(migration={capacity.migration_bytes / gib:.2f} GiB, "
            f"reserve={capacity.reserve_bytes / gib:.2f} GiB)"
        )
    return capacity


def list_order_history_partitions(
    connection: Connection,
    *,
    reference_date: date,
    keep_hot_years: int = 2,
) -> list[PartitionTier]:
    rows = connection.execute(
        text(
            """
            SELECT parent.relname AS parent_name,
                   child.relname AS partition_name,
                   COALESCE(tablespace.spcname, 'pg_default') AS tablespace_name,
                   COALESCE(pg_tablespace_location(tablespace.oid), '') AS tablespace_location,
                   pg_total_relation_size(child.oid) AS size_bytes,
                   (
                       SELECT COUNT(DISTINCT trigger.tgname) = 2
                       FROM pg_trigger trigger
                       WHERE trigger.tgrelid = child.oid
                         AND NOT trigger.tgisinternal
                         AND trigger.tgname IN (
                             'trg_cold_archive_row_guard',
                             'trg_cold_archive_truncate_guard'
                         )
                   ) AS cold_write_protected
            FROM pg_inherits
            JOIN pg_class parent ON parent.oid = inhparent
            JOIN pg_class child ON child.oid = inhrelid
            LEFT JOIN pg_tablespace tablespace ON tablespace.oid = child.reltablespace
            WHERE parent.relname = ANY(CAST(:parent_names AS text[]))
            ORDER BY parent.relname, child.relname
            """
        ),
        {"parent_names": list(ORDER_HISTORY_PARENTS)},
    ).mappings()

    result: list[PartitionTier] = []
    for row in rows:
        year = partition_year(str(row["partition_name"]))
        result.append(
            PartitionTier(
                parent_name=str(row["parent_name"]),
                partition_name=str(row["partition_name"]),
                partition_year=year,
                current_tablespace=str(row["tablespace_name"]),
                tablespace_location=str(row["tablespace_location"] or ""),
                size_bytes=int(row["size_bytes"] or 0),
                desired_tier=desired_partition_tier(
                    year,
                    reference_date=reference_date,
                    keep_hot_years=keep_hot_years,
                ),
                cold_write_protected=bool(row["cold_write_protected"]),
            )
        )
    return result


def _partition_indexes(connection: Connection, partition_name: str) -> list[str]:
    checked_identifier(partition_name)
    return [
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT index_class.relname
                FROM pg_index
                JOIN pg_class table_class ON table_class.oid = indrelid
                JOIN pg_class index_class ON index_class.oid = indexrelid
                JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
                WHERE namespace.nspname = 'public'
                  AND table_class.relname = :partition_name
                ORDER BY index_class.relname
                """
            ),
            {"partition_name": partition_name},
        )
    ]


def partition_row_count(connection: Connection, partition_name: str) -> int:
    partition_name = checked_identifier(partition_name)
    return int(
        connection.execute(
            text(f"SELECT COUNT(*) FROM public.{partition_name}")
        ).scalar_one()
    )


def lock_partition_for_tiering(
    connection: Connection,
    partition_name: str,
    *,
    lock_timeout_seconds: int = 30,
) -> None:
    partition_name = checked_identifier(partition_name)
    if lock_timeout_seconds < 1:
        raise ValueError("lock_timeout_seconds must be at least 1")
    connection.execute(
        text("SELECT set_config('lock_timeout', :timeout, true)"),
        {"timeout": f"{lock_timeout_seconds}s"},
    )
    connection.execute(
        text(
            f"LOCK TABLE public.{partition_name} "
            "IN ACCESS EXCLUSIVE MODE"
        )
    )


def ensure_cold_write_guard_function(connection: Connection) -> None:
    connection.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION public.reject_cold_partition_write()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $function$
            BEGIN
                RAISE EXCEPTION
                    'Partition % is in the read-only cold archive tier', TG_TABLE_NAME
                    USING ERRCODE = '55000';
            END
            $function$
            """
        )
    )


def protect_cold_partition(connection: Connection, partition_name: str) -> None:
    partition_name = checked_identifier(partition_name)
    ensure_cold_write_guard_function(connection)
    connection.execute(
        text(
            f"DROP TRIGGER IF EXISTS trg_cold_archive_row_guard "
            f"ON public.{partition_name}"
        )
    )
    connection.execute(
        text(
            f"CREATE TRIGGER trg_cold_archive_row_guard "
            f"BEFORE INSERT OR UPDATE OR DELETE ON public.{partition_name} "
            "FOR EACH ROW EXECUTE FUNCTION public.reject_cold_partition_write()"
        )
    )
    connection.execute(
        text(
            f"DROP TRIGGER IF EXISTS trg_cold_archive_truncate_guard "
            f"ON public.{partition_name}"
        )
    )
    connection.execute(
        text(
            f"CREATE TRIGGER trg_cold_archive_truncate_guard "
            f"BEFORE TRUNCATE ON public.{partition_name} "
            "FOR EACH STATEMENT EXECUTE FUNCTION public.reject_cold_partition_write()"
        )
    )


def unprotect_partition(connection: Connection, partition_name: str) -> None:
    partition_name = checked_identifier(partition_name)
    connection.execute(
        text(
            f"DROP TRIGGER IF EXISTS trg_cold_archive_row_guard "
            f"ON public.{partition_name}"
        )
    )
    connection.execute(
        text(
            f"DROP TRIGGER IF EXISTS trg_cold_archive_truncate_guard "
            f"ON public.{partition_name}"
        )
    )


def move_partition_to_tablespace(
    connection: Connection,
    *,
    partition_name: str,
    tablespace_name: str,
) -> list[str]:
    partition_name = checked_identifier(partition_name)
    tablespace_name = checked_identifier(tablespace_name)
    tablespace_location(connection, tablespace_name)

    connection.execute(
        text(
            f"ALTER TABLE public.{partition_name} "
            f"SET TABLESPACE {tablespace_name}"
        )
    )
    indexes = _partition_indexes(connection, partition_name)
    for index_name in indexes:
        checked_identifier(index_name)
        connection.execute(
            text(
                f"ALTER INDEX public.{index_name} "
                f"SET TABLESPACE {tablespace_name}"
            )
        )
    return indexes


def set_partition_comment(
    connection: Connection,
    *,
    partition_name: str,
    tier: str,
    tablespace_name: str,
    reviewed_on: date,
) -> None:
    partition_name = checked_identifier(partition_name)
    if tier not in {"hot", "cold"}:
        raise ValueError(f"Unsupported storage tier: {tier}")
    comment = (
        f"retention_tier={tier}; tablespace={tablespace_name}; "
        f"reviewed_on={reviewed_on.isoformat()}"
    )
    connection.execute(
        text(
            f"COMMENT ON TABLE public.{partition_name} IS "
            f"{sql_string_literal(comment)}"
        )
    )
