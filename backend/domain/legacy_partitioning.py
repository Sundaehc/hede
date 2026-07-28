from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class LegacyPartitionTarget:
    parent_name: str
    child_name: str
    partition_key: str
    lower_bound: str
    upper_bound: str
    bound_type: str = "date"

    def __post_init__(self) -> None:
        for identifier in (self.parent_name, self.child_name, self.partition_key):
            if not _IDENTIFIER_PATTERN.fullmatch(identifier):
                raise ValueError(f"Invalid SQL identifier: {identifier}")
        if self.bound_type not in {"date", "integer"}:
            raise ValueError(f"Unsupported partition bound type: {self.bound_type}")
        if self.bound_type == "integer":
            if not self.lower_bound.isdigit() or not self.upper_bound.isdigit():
                raise ValueError("Integer partition bounds must contain digits only")
        else:
            for bound in (self.lower_bound, self.upper_bound):
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", bound):
                    raise ValueError(f"Invalid date partition bound: {bound}")


def partition_parent_exists(bind: Engine | Connection, parent_name: str) -> bool:
    _validate_identifier(parent_name)
    if isinstance(bind, Connection):
        return _partitioned_table_exists(bind, parent_name)
    with bind.connect() as connection:
        return _partitioned_table_exists(connection, parent_name)


def attach_partition_if_parent_exists(bind: Engine | Connection, target: LegacyPartitionTarget) -> bool:
    if not partition_parent_exists(bind, target.parent_name):
        return False
    if isinstance(bind, Connection):
        return _attach_partition_if_needed(bind, target)
    with bind.begin() as connection:
        return _attach_partition_if_needed(connection, target)


def _attach_partition_if_needed(connection: Connection, target: LegacyPartitionTarget) -> bool:
    _set_lock_timeout(connection)
    if _is_attached(connection, target):
        return False
    _prepare_child_for_partition(connection, target)
    _attach_partition(connection, target)
    return True


def migrate_legacy_partitions(engine: Engine, targets: list[LegacyPartitionTarget]) -> list[str]:
    migrated: list[str] = []
    for target in targets:
        with engine.begin() as connection:
            _set_lock_timeout(connection)
            if not _table_exists(connection, target.child_name):
                continue
            _create_parent_and_view(connection, target)
            if _is_attached(connection, target):
                continue
            _prepare_child_for_partition(connection, target)
            _attach_partition(connection, target)
            migrated.append(target.child_name)
    return migrated


def _validate_identifier(identifier: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")


def _qualified(identifier: str) -> str:
    _validate_identifier(identifier)
    return f"public.{identifier}"


def _table_exists(connection: Connection, table_name: str) -> bool:
    return connection.execute(
        text("SELECT to_regclass(:table_name) IS NOT NULL"),
        {"table_name": _qualified(table_name)},
    ).scalar_one()


def _partitioned_table_exists(connection: Connection, table_name: str) -> bool:
    return connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_class
                WHERE oid = CAST(:table_name AS regclass)
                  AND relkind = 'p'
            )
            """
        ),
        {"table_name": _qualified(table_name)},
    ).scalar_one()


def _set_lock_timeout(connection: Connection) -> None:
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))


def _is_attached(connection: Connection, target: LegacyPartitionTarget) -> bool:
    return connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_inherits
                WHERE inhparent = CAST(:parent_name AS regclass)
                  AND inhrelid = CAST(:child_name AS regclass)
            )
            """
        ),
        {"parent_name": _qualified(target.parent_name), "child_name": _qualified(target.child_name)},
    ).scalar_one()


def _create_parent_and_view(connection: Connection, target: LegacyPartitionTarget) -> None:
    parent = _qualified(target.parent_name)
    child = _qualified(target.child_name)
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {parent}
            (LIKE {child} INCLUDING DEFAULTS INCLUDING GENERATED EXCLUDING IDENTITY EXCLUDING CONSTRAINTS EXCLUDING INDEXES)
            PARTITION BY RANGE ({target.partition_key})
            """
        )
    )
    view_name = f"v_{target.parent_name}"
    if not _table_exists(connection, view_name):
        connection.execute(text(f"CREATE VIEW {_qualified(view_name)} AS SELECT * FROM {parent}"))


def _prepare_child_for_partition(connection: Connection, target: LegacyPartitionTarget) -> None:
    child = _qualified(target.child_name)
    identity = connection.execute(
        text(
            """
            SELECT is_identity = 'YES'
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = 'id'
            """
        ),
        {"table_name": target.child_name},
    ).scalar_one_or_none()
    if identity:
        connection.execute(text(f"ALTER TABLE {child} ALTER COLUMN id DROP IDENTITY IF EXISTS"))

    default_expression = connection.execute(
        text(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = 'id'
            """
        ),
        {"table_name": target.child_name},
    ).scalar_one_or_none()
    if not default_expression:
        sequence_name = _sequence_name(target.child_name)
        sequence = _qualified(sequence_name)
        connection.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {sequence}"))
        connection.execute(
            text(
                f"""
                SELECT setval(
                    '{sequence}'::regclass,
                    COALESCE((SELECT max(id) FROM {child}), 1),
                    EXISTS (SELECT 1 FROM {child})
                )
                """
            )
        )
        connection.execute(text(f"ALTER TABLE {child} ALTER COLUMN id SET DEFAULT nextval('{sequence}'::regclass)"))
        connection.execute(text(f"ALTER SEQUENCE {sequence} OWNED BY {child}.id"))

    constraint_name = _range_constraint_name(target)
    constraint_exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = CAST(:child_name AS regclass)
                  AND conname = :constraint_name
            )
            """
        ),
        {"child_name": child, "constraint_name": constraint_name},
    ).scalar_one()
    if not constraint_exists:
        connection.execute(
            text(
                f"""
                ALTER TABLE {child}
                ADD CONSTRAINT {constraint_name}
                CHECK ({target.partition_key} IS NOT NULL
                   AND {target.partition_key} >= {_bound(target, target.lower_bound)}
                   AND {target.partition_key} < {_bound(target, target.upper_bound)}) NOT VALID
                """
            )
        )
    connection.execute(text(f"ALTER TABLE {child} VALIDATE CONSTRAINT {constraint_name}"))


def _attach_partition(connection: Connection, target: LegacyPartitionTarget) -> None:
    connection.execute(
        text(
            f"""
            ALTER TABLE {_qualified(target.parent_name)}
            ATTACH PARTITION {_qualified(target.child_name)}
            FOR VALUES FROM ({_bound(target, target.lower_bound)}) TO ({_bound(target, target.upper_bound)})
            """
        )
    )


def _bound(target: LegacyPartitionTarget, value: str) -> str:
    if target.bound_type == "integer":
        return value
    return f"DATE '{value}'"


def _sequence_name(child_name: str) -> str:
    return f"seq_{sha1(child_name.encode('utf-8')).hexdigest()[:16]}"


def _range_constraint_name(target: LegacyPartitionTarget) -> str:
    digest = sha1(
        f"{target.child_name}:{target.partition_key}:{target.lower_bound}:{target.upper_bound}".encode("utf-8")
    ).hexdigest()[:16]
    return f"ck_partition_{digest}"
