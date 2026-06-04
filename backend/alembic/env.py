from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import load_settings
from domain import fine_table_snapshot_schema, gj_schema, inventory_schema, vip_schema  # noqa: F401 - register tables on METADATA
from domain.schema import METADATA


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = METADATA


def include_object(object_, name, type_, reflected, compare_to):
    if type_ == "index" and reflected and compare_to is None:
        return False
    return True


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    if inspected_type.__class__.__name__ == "TIMESTAMP" and metadata_type.__class__.__name__ == "DateTime":
        return False
    return None


def _database_url() -> str:
    settings = load_settings()
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is required for Alembic migrations")
    return settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=compare_type,
        compare_server_default=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=compare_type,
            compare_server_default=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
