"""Guard compatibility DDL before PostgreSQL takes strong table locks."""
from collections.abc import Mapping

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def ensure_columns(connection: Connection, table_name: str, definitions: Mapping[str, str]) -> dict[str, dict]:
    """Add missing columns and return metadata reflected before any changes."""
    columns = {column["name"]: column for column in inspect(connection).get_columns(table_name)}
    quote = connection.dialect.identifier_preparer.quote
    for name, definition in definitions.items():
        if name not in columns:
            # Definitions are internal SQL constants, never request input.
            connection.execute(text(
                f"ALTER TABLE {quote(table_name)} ADD COLUMN IF NOT EXISTS {quote(name)} {definition}"
            ))
    return columns


def ensure_not_null(connection: Connection, table_name: str, *column_names: str) -> None:
    columns = {column["name"]: column for column in inspect(connection).get_columns(table_name)}
    quote = connection.dialect.identifier_preparer.quote
    for name in column_names:
        if columns[name]["nullable"]:
            connection.execute(text(
                f"ALTER TABLE {quote(table_name)} ALTER COLUMN {quote(name)} SET NOT NULL"
            ))
