from sqlalchemy import create_engine, event

from domain.product_size_group_mapping_schema import PRODUCT_SIZE_GROUP_MAPPINGS_TABLE
from domain.schema import PRODUCT_TABLES
from domain.size_group_schema import SIZE_GROUP_ITEMS_TABLE, SIZE_GROUPS_TABLE
from storage.size_group_repository import SizeGroupInUseError, SizeGroupRepository


def make_repository():
    engine = create_engine("sqlite://")
    event.listen(
        engine,
        "connect",
        lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value),
    )
    SIZE_GROUPS_TABLE.create(engine)
    SIZE_GROUP_ITEMS_TABLE.create(engine)
    PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.create(engine)
    for table in PRODUCT_TABLES.values():
        table.create(engine)
    return SizeGroupRepository(engine), engine


def test_size_group_crud_and_rename_updates_products():
    repository, engine = make_repository()
    created = repository.create_group(
        name="女鞋常规",
        items=[
            {"size_name": "34", "barcode": "code-34"},
            {"size_name": "35", "barcode": "code-35"},
        ],
    )

    assert created["name"] == "女鞋常规"
    assert [item["size_name"] for item in created["items"]] == ["34", "35"]

    product_table = PRODUCT_TABLES["cbanner_womens"]
    with engine.begin() as connection:
        connection.execute(product_table.insert().values(
            id=1,
            source_workbook="test",
            source_sheet="test",
            source_row_number="1",
            raw_payload={},
            sku="TEST-01",
            size_range="女鞋常规",
        ))

    updated = repository.update_group(
        created["id"],
        name="女鞋 34-35",
        items=[{"size_name": "34", "barcode": "new-34"}],
    )

    assert updated is not None
    assert updated["name"] == "女鞋 34-35"
    assert updated["product_count"] == 1
    with engine.connect() as connection:
        assert connection.execute(product_table.select()).mappings().one()["size_range"] == "女鞋 34-35"

    try:
        repository.delete_group(created["id"])
    except SizeGroupInUseError as exc:
        assert exc.product_count == 1
    else:
        raise AssertionError("expected in-use size group deletion to fail")


def test_size_group_requires_unique_size_and_barcode():
    repository, _engine = make_repository()

    try:
        repository.create_group(
            name="重复尺码",
            items=[
                {"size_name": "34", "barcode": "code-1"},
                {"size_name": "34", "barcode": "code-2"},
            ],
        )
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("expected duplicate size to fail")


def test_size_group_rename_updates_product_size_mappings():
    repository, engine = make_repository()
    created = repository.create_group(
        name="旧尺码段",
        items=[{"size_name": "34", "barcode": "code-34"}],
    )
    with engine.begin() as connection:
        connection.execute(PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.insert().values(
            product_code="TEST-01",
            size_group_name="旧尺码段",
            source_workbook="test.xlsx",
            source_sheet="汇总",
            source_row_number="2",
        ))

    updated = repository.update_group(
        created["id"],
        name="新尺码段",
        items=[{"size_name": "34", "barcode": "code-34"}],
    )

    assert updated is not None
    with engine.connect() as connection:
        assert connection.execute(
            PRODUCT_SIZE_GROUP_MAPPINGS_TABLE.select()
        ).mappings().one()["size_group_name"] == "新尺码段"
