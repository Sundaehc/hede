from __future__ import annotations

import json
import re
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text

from api.routes import inventory as inventory_routes
from domain.inventory_sources import ACCOUNTING_DOCUMENT_TYPES, DOCUMENT_TYPES
from domain.product_archive_identity_schema import (
    HISTORY_PRODUCT_SYNC_FIELDS,
    PURCHASE_PRODUCT_EXTRA_FIELD_MAPPING,
    _backfill_inventory_product_details,
    _install_functions,
    _install_inventory_product_link_triggers,
    _sync_archive_table,
    product_archive_identity_coverage,
)
from storage.inventory_repository import InventoryRepository


@pytest.fixture
def identity_connection(test_database_url):
    engine = create_engine(test_database_url)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.skip("PostgreSQL is required for product identity triggers")
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET LOCAL search_path TO pg_temp"))
                connection.execute(text("SET LOCAL statement_timeout = '30s'"))
                statements = [
                    """CREATE TEMP TABLE inventory_records (
                        id bigint PRIMARY KEY, document_type text, supplier text,
                        raw_payload json, amount numeric, updated_at timestamptz DEFAULT now()
                    ) ON COMMIT DROP""",
                    """CREATE TEMP TABLE product_archive_identities (
                        id bigserial PRIMARY KEY, brand text, source_table text,
                        source_product_id bigint, sku text, original_sku text,
                        is_active boolean DEFAULT true, updated_at timestamptz DEFAULT now(),
                        UNIQUE (source_table, source_product_id)
                    ) ON COMMIT DROP""",
                    """CREATE TEMP TABLE inventory_details (
                        id bigint PRIMARY KEY, document_id bigint REFERENCES inventory_records(id),
                        product_identity_id bigint REFERENCES product_archive_identities(id),
                        product_code text, product_name text, color_barcode text, color_name text, color_spec text, extra_fields json,
                        quantity numeric, unit_price numeric, amount numeric,
                        size_quantities json, remark text, updated_at timestamptz DEFAULT now()
                    ) ON COMMIT DROP""",
                    """CREATE TEMP TABLE suppliers (
                        id bigserial PRIMARY KEY, name text, brand text
                    ) ON COMMIT DROP""",
                    """CREATE TEMP TABLE test_product_archive (
                        id bigint PRIMARY KEY, sku text, original_sku text, deleted_at timestamptz,
                        product_name text, color_code text, color text, size_range text, cost numeric,
                        factory_sku text, upper_material text, lining_material text,
                        outsole_material text, insole_material text, shoe_box_spec text
                    ) ON COMMIT DROP""",
                    """CREATE TEMP TABLE size_groups (id bigint PRIMARY KEY, name text) ON COMMIT DROP""",
                    """CREATE TEMP TABLE size_group_items (
                        id bigint PRIMARY KEY, size_group_id bigint, size_name text, sort_order integer
                    ) ON COMMIT DROP""",
                ]
                for statement in statements:
                    connection.execute(text(statement))
                event.listen(
                    connection,
                    "before_cursor_execute",
                    lambda _connection, _cursor, statement, parameters, _context, _executemany: (
                        re.sub(r"(?<![\w.])(hede_[a-z_]+)\(", r"pg_temp.\1(", statement),
                        parameters,
                    ),
                    retval=True,
                )
                _install_functions(connection)
                _sync_archive_table(connection, "test_product_archive", "cbanner_mens")
                _install_inventory_product_link_triggers(connection)
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _product(connection, product_id=1, sku="OLD-CODE", original_sku="ORIGINAL-CODE"):
    connection.execute(text("""
        INSERT INTO test_product_archive (id, sku, original_sku)
        VALUES (:product_id, :sku, :original_sku)
    """), {"product_id": product_id, "sku": sku, "original_sku": original_sku})
    return connection.execute(text("""
        SELECT id FROM product_archive_identities
        WHERE source_table = 'test_product_archive' AND source_product_id = :product_id
    """), {"product_id": product_id}).scalar_one()


def _document(connection, document_id=1, document_type="进货单", *, brand="cbanner_mens", supplier="测试供应商"):
    connection.execute(text("""
        INSERT INTO inventory_records (id, document_type, supplier, raw_payload)
        VALUES (:document_id, :document_type, :supplier, CAST(:payload AS json))
    """), {
        "document_id": document_id, "document_type": document_type,
        "supplier": supplier, "payload": json.dumps({"brand": brand} if brand else {}),
    })


def _detail(connection, detail_id=1, document_id=1, *, code="OLD-CODE", identity_id=None, name="测试鞋", color="24"):
    connection.execute(text("""
        INSERT INTO inventory_details (
            id, document_id, product_identity_id, product_code, product_name, color_barcode,
            quantity, unit_price, amount, size_quantities, extra_fields, remark
        ) VALUES (
            :detail_id, :document_id, :identity_id, :code, :name, :color,
            2, 123.45, 246.90, '{"230":"2"}',
            '{"style_code":"OLD-CODE","image_code":"ORIGINAL-CODE","other":"keep"}', '保持备注'
        )
    """), {
        "detail_id": detail_id, "document_id": document_id,
        "identity_id": identity_id, "code": code, "name": name, "color": color,
    })


def _other_brand_identity(connection, sku="OLD-CODE"):
    return connection.execute(text("""
        INSERT INTO product_archive_identities (brand, source_table, source_product_id, sku, original_sku)
        VALUES ('cbanner_womens', 'other_archive', 1, :sku, 'OTHER-ORIGINAL')
        RETURNING id
    """), {"sku": sku}).scalar_one()


@pytest.mark.parametrize("document_type", DOCUMENT_TYPES)
@pytest.mark.parametrize("explicit_identity", [False, True])
def test_all_document_types_link_but_only_purchase_follows_archive_code_changes(
    identity_connection, document_type, explicit_identity,
):
    connection = identity_connection
    identity_id = _product(connection)
    _document(connection, document_type=document_type)
    _detail(connection, identity_id=identity_id if explicit_identity else None)
    connection.execute(text("""
        UPDATE test_product_archive SET sku = 'NEW-CODE', original_sku = 'NEW-ORIGINAL' WHERE id = 1
    """))

    detail = connection.execute(text("SELECT * FROM inventory_details WHERE id = 1")).mappings().one()
    assert detail["product_identity_id"] == identity_id
    is_purchase = document_type == "进货订单"
    assert detail["product_code"] == ("NEW-CODE" if is_purchase else "OLD-CODE")
    assert detail["extra_fields"] == {
        "style_code": "NEW-CODE" if is_purchase else "OLD-CODE",
        "image_code": "NEW-ORIGINAL" if is_purchase else "ORIGINAL-CODE", "other": "keep",
    }
    assert (detail["quantity"], detail["unit_price"], detail["amount"]) == (Decimal("2"), Decimal("123.45"), Decimal("246.90"))
    assert detail["size_quantities"] == {"230": "2"}
    assert detail["remark"] == "保持备注"
    assert InventoryRepository.document_product_identity_scope(connection, identity_id) == {
        "details": 1, "documents": 1, "document_ids": [1],
    }


@pytest.mark.parametrize("document_type", DOCUMENT_TYPES)
def test_archive_attributes_sync_by_document_type(identity_connection, document_type):
    connection = identity_connection
    identity_id = _product(connection)
    _document(connection, document_type=document_type)
    _detail(connection)
    connection.execute(text("UPDATE inventory_details SET color_name='旧颜色', color_spec='旧规格'"))
    connection.execute(text("INSERT INTO size_groups VALUES (1, '新尺码组')"))
    connection.execute(text("INSERT INTO size_group_items VALUES (1, 1, '39', 2), (2, 1, '38', 1)"))
    connection.execute(text("UPDATE inventory_records SET amount=246.90"))
    connection.execute(text("""
        UPDATE test_product_archive SET sku='NEW-CODE', original_sku='NEW-ORIGINAL',
            product_name='新鞋名', color_code='80', color='黑色', size_range='新尺码组', cost=88.88,
            factory_sku='NEW-FACTORY', upper_material='新鞋面', lining_material='新内里',
            outsole_material='新大底', insole_material='新鞋垫', shoe_box_spec='新鞋盒'
        WHERE id=1
    """))
    detail = connection.execute(text("SELECT * FROM inventory_details")).mappings().one()
    is_purchase = document_type == '进货订单'
    assert detail['product_identity_id'] == identity_id
    assert detail['product_code'] == ('NEW-CODE' if is_purchase else 'OLD-CODE')
    assert detail['product_name'] == ('新鞋名' if is_purchase else '测试鞋')
    assert detail['color_barcode'] == '80'
    assert detail['color_name'] == '黑色'
    assert detail['color_spec'] == ('黑色' if is_purchase else '旧规格')
    assert detail['unit_price'] == Decimal('88.88' if is_purchase else '123.45')
    assert detail['amount'] == Decimal('177.76' if is_purchase else '246.90')
    assert connection.scalar(text('SELECT amount FROM inventory_records')) == detail['amount']
    assert detail['quantity'] == Decimal('2')
    assert detail['size_quantities'] == {'230': '2'}
    assert detail['remark'] == '保持备注'
    expected_extra = {
        'style_code': 'NEW-CODE' if is_purchase else 'OLD-CODE',
        'image_code': 'NEW-ORIGINAL' if is_purchase else 'ORIGINAL-CODE',
        'other': 'keep', 'size_range': '新尺码组', 'size_labels': '38|39',
    }
    if is_purchase:
        expected_extra.update({
            'factory_code': 'NEW-FACTORY', 'upper_material': '新鞋面', 'lining_material': '新内里',
            'outsole_material': '新大底', 'insole_material': '新鞋垫', 'shoe_box_spec': '新鞋盒',
        })
    assert detail['extra_fields'] == expected_extra


@pytest.mark.parametrize('document_type', ['进货订单', '进货单'])
def test_archive_clearing_fields_preserves_unrelated_values(identity_connection, document_type):
    connection = identity_connection
    _product(connection)
    connection.execute(text("UPDATE test_product_archive SET color='黑色', color_code='80', size_range='旧组', upper_material='皮革'"))
    _document(connection, document_type=document_type)
    _detail(connection)
    connection.execute(text("""UPDATE inventory_details SET color_name='黑色', color_spec='规格保留',
        extra_fields='{"size_range":"old","size_labels":"38|39","upper_material":"manual","other":"keep"}'"""))
    connection.execute(text("UPDATE test_product_archive SET color=NULL, color_code=NULL, size_range=NULL, upper_material=NULL"))
    detail = connection.execute(text('SELECT * FROM inventory_details')).mappings().one()
    assert detail['color_name'] is None
    assert detail['color_barcode'] is None
    assert detail['extra_fields'] == {
        'size_range': '', 'size_labels': '', 'other': 'keep',
        'upper_material': '' if document_type == '进货订单' else 'manual',
    }
    assert detail['unit_price'] == Decimal('123.45')
    assert detail['size_quantities'] == {'230': '2'}


def test_history_save_after_archive_rename_keeps_identity_and_original_code(identity_connection):
    connection = identity_connection
    identity_id = _product(connection)
    _document(connection)
    _detail(connection)
    connection.execute(text("UPDATE test_product_archive SET sku='NEW-CODE'"))
    connection.execute(text("UPDATE inventory_details SET product_code=product_code, product_identity_id=product_identity_id, remark='changed'"))
    connection.execute(text("UPDATE inventory_records SET raw_payload='{\"brand\":\"cbanner_mens\",\"note\":\"changed\"}'"))
    connection.execute(text("UPDATE test_product_archive SET color='黑色'"))
    assert connection.execute(text('SELECT product_identity_id, product_code, color_name FROM inventory_details')).one() == (identity_id, 'OLD-CODE', '黑色')


@pytest.mark.parametrize('document_type', ['进货订单', '进货单'])
@pytest.mark.parametrize(('field', 'value'), [
    ('color', '黑色'), ('color_code', '80'), ('size_range', '新组'),
    ('product_name', '新鞋名'), ('cost', '100'),
    *[(field, 'changed') for field in PURCHASE_PRODUCT_EXTRA_FIELD_MAPPING],
])
def test_single_field_update_only_changes_corresponding_detail_fields(identity_connection, document_type, field, value):
    connection = identity_connection
    _product(connection)
    _document(connection, document_type=document_type)
    _detail(connection)
    before = dict(connection.execute(text('SELECT * FROM inventory_details')).mappings().one())
    connection.execute(text(f'UPDATE test_product_archive SET {field}=:value'), {'value': value})
    after = dict(connection.execute(text('SELECT * FROM inventory_details')).mappings().one())
    before.pop('updated_at')
    after.pop('updated_at')
    expected = {**before, 'extra_fields': dict(before['extra_fields'])}
    if document_type == '进货订单' or field in HISTORY_PRODUCT_SYNC_FIELDS:
        if field == 'color':
            expected['color_name'] = value
            if document_type == '进货订单':
                expected['color_spec'] = value
        elif field == 'color_code':
            expected['color_barcode'] = value
        elif field == 'size_range':
            expected['extra_fields'].update(size_range=value, size_labels='')
        elif field == 'cost':
            expected.update(unit_price=Decimal(value), amount=Decimal(value) * 2)
        elif field == 'product_name':
            expected['product_name'] = value
        else:
            expected['extra_fields'][PURCHASE_PRODUCT_EXTRA_FIELD_MAPPING[field]] = value
    assert after == expected
    connection.execute(text("UPDATE inventory_details SET updated_at='2000-01-01'"))
    connection.execute(text(f'UPDATE test_product_archive SET {field}=:value'), {'value': value})
    assert connection.scalar(text('SELECT extract(year FROM updated_at) FROM inventory_details')) == 2000


def test_purchase_cost_change_recalculates_whole_order_amount(identity_connection):
    connection = identity_connection
    _product(connection)
    _document(connection, document_type='进货订单')
    _detail(connection)
    _detail(connection, detail_id=2, code='UNRELATED')
    connection.execute(text('UPDATE test_product_archive SET cost=100'))
    assert connection.scalar(text('SELECT amount FROM inventory_records')) == Decimal('446.90')
    assert connection.execute(text('SELECT unit_price, amount FROM inventory_details WHERE id=2')).one() == (Decimal('123.45'), Decimal('246.90'))


def test_attribute_sync_rollback_restores_purchase_and_history(identity_connection):
    connection = identity_connection
    _product(connection)
    _document(connection, document_type='进货订单')
    _document(connection, 2, '进货单')
    _detail(connection)
    _detail(connection, 2, 2)
    before = [dict(row) for row in connection.execute(text('SELECT * FROM inventory_details ORDER BY id')).mappings()]
    savepoint = connection.begin_nested()
    connection.execute(text("UPDATE test_product_archive SET color='黑色', cost=100, size_range='new'"))
    assert connection.scalar(text("SELECT count(*) FROM inventory_details WHERE color_name='黑色'")) == 2
    savepoint.rollback()
    assert [dict(row) for row in connection.execute(text('SELECT * FROM inventory_details ORDER BY id')).mappings()] == before


def test_backfill_links_historical_rows_for_every_document_type(identity_connection):
    connection = identity_connection
    identity_id = _product(connection)
    connection.execute(text("ALTER TABLE inventory_details DISABLE TRIGGER trg_hede_purchase_detail_product_link"))
    for document_id, document_type in enumerate(DOCUMENT_TYPES, start=1):
        _document(connection, document_id, document_type)
        _detail(connection, document_id, document_id)
    connection.execute(text("ALTER TABLE inventory_details ENABLE TRIGGER trg_hede_purchase_detail_product_link"))

    _backfill_inventory_product_details(connection)
    _backfill_inventory_product_details(connection)

    assert connection.execute(text("SELECT count(*) FROM inventory_details WHERE product_identity_id = :identity_id"), {"identity_id": identity_id}).scalar_one() == len(DOCUMENT_TYPES)
    connection.execute(text("UPDATE test_product_archive SET sku = 'NEW-CODE' WHERE id = 1"))
    assert connection.execute(text("SELECT count(*) FROM inventory_details WHERE product_code = 'NEW-CODE'")).scalar_one() == 1
    assert connection.execute(text("SELECT count(*) FROM inventory_details WHERE product_code = 'OLD-CODE'")).scalar_one() == len(DOCUMENT_TYPES) - 1
    coverage = product_archive_identity_coverage(connection)
    assert coverage["linked_product_details"] == len(DOCUMENT_TYPES)
    assert coverage["linked_non_purchase_details"] == len(DOCUMENT_TYPES) - 1
    assert coverage["unlinked_product_details"] == 0


@pytest.mark.parametrize("document_type", ACCOUNTING_DOCUMENT_TYPES)
def test_fee_lines_without_product_code_remain_unlinked(identity_connection, document_type):
    connection = identity_connection
    identity_id = _product(connection, sku="罚款")
    _document(connection, document_type=document_type)
    _detail(connection, code="", name="罚款", identity_id=identity_id)
    _backfill_inventory_product_details(connection)
    connection.execute(text("UPDATE test_product_archive SET sku = '新货号' WHERE id = 1"))

    row = connection.execute(text("SELECT product_code, product_identity_id, product_name, amount FROM inventory_details")).one()
    assert row == ("", None, "罚款", Decimal("246.90"))


def test_rename_preserves_explicit_identity_when_new_code_exists_in_another_brand(identity_connection):
    connection = identity_connection
    identity_id = _product(connection)
    _other_brand_identity(connection, sku="NEW-CODE")
    _document(connection, document_type="批发销售单", brand=None)
    _detail(connection, identity_id=identity_id)

    connection.execute(text("UPDATE test_product_archive SET sku = 'NEW-CODE' WHERE id = 1"))

    assert connection.execute(text("SELECT product_identity_id, product_code FROM inventory_details")).one() == (identity_id, "OLD-CODE")


def test_ambiguous_unbranded_codes_are_not_linked_or_renamed(identity_connection):
    connection = identity_connection
    _product(connection)
    _other_brand_identity(connection)
    _document(connection, document_type="同价调拨单", brand=None)
    _detail(connection)
    _detail(connection, 2, code="OLD-CODE-SUFFIX")

    _backfill_inventory_product_details(connection)
    connection.execute(text("UPDATE test_product_archive SET sku = 'NEW-CODE' WHERE id = 1"))

    assert connection.execute(text("SELECT product_identity_id, product_code FROM inventory_details ORDER BY id")).all() == [
        (None, "OLD-CODE"), (None, "OLD-CODE-SUFFIX"),
    ]


@pytest.mark.parametrize("document_type", ["批发销售单", "批发销售退货单", "同价调拨单", "报溢单", "应收款增加"])
@pytest.mark.parametrize("historical", [False, True])
def test_customers_and_warehouses_are_not_mistaken_for_suppliers(identity_connection, document_type, historical):
    connection = identity_connection
    identity_id = _product(connection)
    connection.execute(text("INSERT INTO suppliers (name, brand) VALUES ('同名单位', 'cbanner_womens')"))
    _document(connection, document_type=document_type, brand=None, supplier="同名单位")
    if historical:
        connection.execute(text("ALTER TABLE inventory_details DISABLE TRIGGER trg_hede_purchase_detail_product_link"))
    _detail(connection)
    if historical:
        connection.execute(text("ALTER TABLE inventory_details ENABLE TRIGGER trg_hede_purchase_detail_product_link"))
        _backfill_inventory_product_details(connection)

    assert connection.execute(text("SELECT product_identity_id FROM inventory_details")).scalar_one() == identity_id


@pytest.mark.parametrize("document_type", ["进货订单", "进货单", "进货退货单"])
def test_supplier_brand_limits_automatic_linking(identity_connection, document_type):
    connection = identity_connection
    _product(connection)
    other_identity_id = _other_brand_identity(connection)
    connection.execute(text("INSERT INTO suppliers (name, brand) VALUES ('女鞋供应商', 'cbanner_womens')"))
    _document(connection, document_type=document_type, brand=None, supplier="女鞋供应商")
    _detail(connection)
    _backfill_inventory_product_details(connection)
    connection.execute(text("UPDATE test_product_archive SET sku = 'NEW-CODE' WHERE id = 1"))

    assert connection.execute(text("SELECT product_identity_id, product_code FROM inventory_details")).one() == (other_identity_id, "OLD-CODE")


@pytest.mark.parametrize("historical", [False, True])
def test_original_sku_resolves_unique_color_variant(identity_connection, historical):
    connection = identity_connection
    identity_id = _product(connection, sku="STYLE24", original_sku="STYLE")
    _product(connection, product_id=2, sku="STYLE35", original_sku="STYLE")
    _document(connection, document_type="进货退货单")
    if historical:
        connection.execute(text("ALTER TABLE inventory_details DISABLE TRIGGER trg_hede_purchase_detail_product_link"))
    _detail(connection, code="STYLE", name="STYLE24白色", color="24")
    if historical:
        connection.execute(text("ALTER TABLE inventory_details ENABLE TRIGGER trg_hede_purchase_detail_product_link"))
        _backfill_inventory_product_details(connection)

    assert connection.execute(text("SELECT product_identity_id, product_code FROM inventory_details")).one() == (identity_id, "STYLE24")


def test_editing_detail_code_relinks_to_new_product(identity_connection):
    connection = identity_connection
    _product(connection)
    second_identity = _product(connection, product_id=2, sku="SECOND-CODE")
    _document(connection, document_type="报损单")
    _detail(connection)

    connection.execute(text("UPDATE inventory_details SET product_code = 'SECOND-CODE' WHERE id = 1"))
    connection.execute(text("UPDATE test_product_archive SET sku = 'NEW-CODE' WHERE id = 1"))

    assert connection.execute(text("SELECT product_identity_id, product_code FROM inventory_details")).one() == (second_identity, "SECOND-CODE")


def test_document_type_and_brand_changes_relink_details(identity_connection):
    connection = identity_connection
    identity_id = _product(connection)
    other_identity_id = _other_brand_identity(connection)
    _document(connection)
    _detail(connection)
    connection.execute(text("UPDATE inventory_records SET document_type = '批发销售退货单' WHERE id = 1"))
    assert connection.execute(text("SELECT product_identity_id FROM inventory_details")).scalar_one() == identity_id
    connection.execute(text("UPDATE inventory_records SET raw_payload = '{\"brand\":\"cbanner_womens\"}' WHERE id = 1"))
    assert connection.execute(text("SELECT product_identity_id FROM inventory_details")).scalar_one() == other_identity_id


def test_archive_rename_rollback_restores_all_document_codes(identity_connection):
    connection = identity_connection
    _product(connection)
    _document(connection, document_type="进货订单")
    _detail(connection)
    savepoint = connection.begin_nested()
    connection.execute(text("UPDATE test_product_archive SET sku = 'NEW-CODE' WHERE id = 1"))
    assert connection.execute(text("SELECT product_code FROM inventory_details")).scalar_one() == "NEW-CODE"
    savepoint.rollback()
    assert connection.execute(text("SELECT product_code FROM inventory_details")).scalar_one() == "OLD-CODE"


@pytest.mark.parametrize("document_type", DOCUMENT_TYPES)
def test_manual_detail_save_preserves_product_identity_for_all_types(monkeypatch, document_type):
    repository = Mock(spec=InventoryRepository)
    repository.get_record.return_value = {"id": 1, "document_type": document_type}
    repository.create_detail.side_effect = lambda payload: {"id": 1, **payload}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(inventory_repository=repository)))
    monkeypatch.setattr(inventory_routes, "_apply_product_archive_cost", lambda _repository, _record, payload: payload)
    monkeypatch.setattr(inventory_routes, "_gendered_detail_payloads", lambda _repository, _record, payload: [payload])
    monkeypatch.setattr(inventory_routes, "_log_detail_operation", lambda *_args, **_kwargs: None)

    result = inventory_routes.create_inventory_detail(request, 1, {"product_code": "TEST", "product_identity_id": "42"})

    assert result["item"]["product_identity_id"] == 42
    assert repository.create_detail.call_args.args[0]["product_identity_id"] == 42


def test_partial_detail_update_does_not_clear_identity():
    payload = {"amount": "100"}
    inventory_routes._normalize_inventory_product_identity(payload)
    assert "product_identity_id" not in payload


def test_blank_product_code_clears_identity():
    payload = {"product_code": "", "product_identity_id": "42"}
    inventory_routes._normalize_inventory_product_identity(payload)
    assert payload["product_identity_id"] is None


@pytest.mark.parametrize("value", ["invalid", "0", "-1"])
def test_invalid_identity_is_rejected(value):
    with pytest.raises(HTTPException) as error:
        inventory_routes._normalize_inventory_product_identity({"product_code": "TEST", "product_identity_id": value})
    assert error.value.status_code == 400
