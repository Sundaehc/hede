from __future__ import annotations

import importlib.util
import io
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from openpyxl import load_workbook
from sqlalchemy import MetaData, create_engine, event, insert, select

from api.routes.import_export import _build_product_import_template
from api.schemas import ProductPayload
from domain.fields import PRODUCT_FIELDS
from domain.schema import PRODUCT_ARCHIVE_TABLES, build_product_archive_table
from storage.db import Database
from storage.product_repository import ProductRepository
from transform.rows import build_admin_record, build_canonical_row


def test_archive_factory_shipping_price_retains_original_cost_column() -> None:
    fields = {field.name: field for field in PRODUCT_FIELDS}
    assert fields["cost"].label == "工厂出货价"
    assert fields["cost_price"].label == "成本价"
    for table in (*PRODUCT_ARCHIVE_TABLES.values(), build_product_archive_table("manual_product_archive_999", metadata=MetaData())):
        assert table.c.cost_price.nullable
        assert table.c.cost_price.server_default is None
        assert table.c.cost_price.type.precision == 10
        assert table.c.cost_price.type.scale == 2


@pytest.mark.parametrize("shipping_header", ["成本", "工厂出货价"])
def test_workbook_import_separates_shipping_and_cost_prices(shipping_header: str) -> None:
    row = build_canonical_row(
        {"货号": "PRICES-001", shipping_header: "118", "成本价": "136.50"},
        workbook_key="cbanner_mens_26", sheet_name="26年春季款", row_number=2, image_path=None,
    )
    assert row["cost"] == Decimal("118")
    assert row["cost_price"] == Decimal("136.50")


def test_original_cost_import_leaves_cost_price_empty() -> None:
    row = build_canonical_row(
        {"货号": "PRICES-002", "成本": "118"}, workbook_key="cbanner_mens_26",
        sheet_name="26年春季款", row_number=2, image_path=None,
    )
    assert row["cost"] == Decimal("118")
    assert row["cost_price"] is None
    payload = ProductPayload(sku="PRICES-002", cost="118", cost_price="0")
    record = build_admin_record("cbanner_mens", payload.model_dump())
    assert record["cost"] == Decimal("118")
    assert record["cost_price"] == Decimal("0")


def test_import_template_uses_distinct_price_headers() -> None:
    workbook = load_workbook(io.BytesIO(_build_product_import_template().getvalue()))
    headers = [cell.value for cell in workbook["商品导入模板"][1]]
    assert "工厂出货价" in headers
    assert "成本价" in headers
    assert "成本" not in headers
    workbook.close()


def test_price_migration_adds_nullable_column_without_updating_original_values(monkeypatch) -> None:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20261009_0076_product_cost_price.py"
    specification = importlib.util.spec_from_file_location("product_cost_price_migration", path)
    migration = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(migration)
    execute = Mock()
    monkeypatch.setattr(migration.op, "execute", execute)
    migration.upgrade()
    statements = [call.args[0] for call in execute.call_args_list]
    assert len(statements) == 7
    assert all("ADD COLUMN IF NOT EXISTS cost_price NUMERIC(10, 2)" in statement for statement in statements)
    assert all("UPDATE " not in statement and "DEFAULT " not in statement for statement in statements)
    assert "manual_product_archive_[0-9]+" in statements[-1]
    execute.reset_mock()
    migration.downgrade()
    assert all("DROP COLUMN IF EXISTS cost_price" in call.args[0] for call in execute.call_args_list)


@pytest.fixture
def price_repository():
    engine = create_engine("sqlite://", json_serializer=lambda value: json.dumps(value, default=str))
    event.listen(engine, "connect", lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value))
    table = PRODUCT_ARCHIVE_TABLES["cbanner_mens"]
    table.create(engine)
    repository = object.__new__(ProductRepository)
    repository.engine = engine
    repository._color_code_cache = {}
    try:
        yield repository, table
    finally:
        engine.dispose()


def test_edit_cost_price_does_not_change_shipping_override(price_repository) -> None:
    repository, table = price_repository
    with repository.engine.begin() as connection:
        connection.execute(insert(table).values(id=1, **build_admin_record("cbanner_mens", {"sku": "PRICES-EDIT", "cost": "118"})))
    updated = repository.update_product("cbanner_mens", 1, build_admin_record("cbanner_mens", {"sku": "PRICES-EDIT", "cost": "118", "cost_price": "136.50"}), manual_cost_override=True)
    assert updated["cost"] == Decimal("118")
    assert updated["cost_price"] == Decimal("136.50")
    assert updated["cost_manual_override"] is False
    updated = repository.update_product("cbanner_mens", 1, build_admin_record("cbanner_mens", {"sku": "PRICES-EDIT", "cost": "120", "cost_price": None}), manual_cost_override=True)
    assert updated["cost"] == Decimal("120")
    assert updated["cost_price"] is None
    assert updated["cost_manual_override"] is True


@pytest.mark.parametrize("method", ["replace_brand_rows", "upsert_brand_rows"])
def test_archive_import_preserves_maintained_cost_price(price_repository, method: str) -> None:
    repository, table = price_repository
    with repository.engine.begin() as connection:
        connection.execute(insert(table).values(id=1, **build_admin_record("cbanner_mens", {"sku": "PRICES-SYNC", "cost": "118", "cost_price": "136.50"})))
    database = object.__new__(Database)
    database.engine = repository.engine
    getattr(database, method)("cbanner_mens", [{"id": 2, **build_admin_record("cbanner_mens", {"sku": "PRICES-SYNC", "cost": "119"})}])
    with repository.engine.connect() as connection:
        row = connection.execute(select(table)).mappings().one()
    assert row["cost"] == Decimal("119")
    assert row["cost_price"] == Decimal("136.50")
