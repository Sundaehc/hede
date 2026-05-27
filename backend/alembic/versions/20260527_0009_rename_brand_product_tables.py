"""rename brand product tables

Revision ID: 20260527_0009
Revises: 20260527_0008
Create Date: 2026-05-27 00:09:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260527_0009"
down_revision: str | None = "20260527_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RENAMES = (
    ("qbd_mens_products", "cbanner_mens_products"),
    ("qbd_womens_products", "cbanner_womens_products"),
    ("yiban_products", "eblan_products"),
)


def upgrade() -> None:
    _rename_tables(RENAMES)


def downgrade() -> None:
    _rename_tables(tuple((new, old) for old, new in reversed(RENAMES)))


def _rename_tables(renames: tuple[tuple[str, str], ...]) -> None:
    bind = op.get_bind()
    for old_name, new_name in renames:
        old_exists = bind.exec_driver_sql("SELECT to_regclass(%s)", (old_name,)).scalar()
        new_exists = bind.exec_driver_sql("SELECT to_regclass(%s)", (new_name,)).scalar()
        if old_exists and not new_exists:
            op.rename_table(old_name, new_name)

    for old_name, new_name in renames:
        _rename_constraint(f"uq_{old_name}_sku", f"uq_{new_name}_sku")
        _rename_index(f"idx_{old_name}_year", f"idx_{new_name}_year")
        _rename_index(f"idx_{old_name}_sku_trgm", f"idx_{new_name}_sku_trgm")
        _rename_index(f"idx_{old_name}_original_sku_trgm", f"idx_{new_name}_original_sku_trgm")


def _rename_constraint(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    exists = bind.exec_driver_sql("SELECT to_regclass(%s)", (old_name,)).scalar()
    target_exists = bind.exec_driver_sql("SELECT to_regclass(%s)", (new_name,)).scalar()
    if exists and not target_exists:
        op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')


def _rename_index(old_name: str, new_name: str) -> None:
    bind = op.get_bind()
    exists = bind.exec_driver_sql("SELECT to_regclass(%s)", (old_name,)).scalar()
    target_exists = bind.exec_driver_sql("SELECT to_regclass(%s)", (new_name,)).scalar()
    if exists and not target_exists:
        op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')
