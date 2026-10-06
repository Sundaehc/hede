from sqlalchemy import create_engine, event

from api.schemas import ProductWriteRequest
from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES, PRODUCT_TABLES
from pipeline.import_pipeline import GJ_PRODUCT_BRANDS
from storage.product_repository import ProductRepository


def test_smiley_uses_an_editable_archive_without_joining_operational_brand_tables():
    assert PRODUCT_ARCHIVE_TABLES["smiley"].name == "smiley_products"
    assert PRODUCT_ARCHIVE_TABLES["ni"].name == "ni_products"
    assert "smiley" not in PRODUCT_TABLES
    assert "ni" not in PRODUCT_TABLES
    assert "smiley" in GJ_PRODUCT_BRANDS
    assert "ni" in GJ_PRODUCT_BRANDS


def test_product_mutation_schema_accepts_smiley():
    request = ProductWriteRequest.model_validate({
        "brand": "smiley",
        "payload": {"sku": "SMILEY-001"},
    })

    assert request.brand == "smiley"

    ni_request = ProductWriteRequest.model_validate({
        "brand": "ni",
        "payload": {"sku": "NI-001"},
    })
    assert ni_request.brand == "ni"


def test_smiley_product_write_keeps_manual_code_and_fills_mapped_color():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    COLOR_BARCODE_TABLE.create(engine)
    with engine.begin() as connection:
        connection.execute(COLOR_BARCODE_TABLE.insert().values(
            id=1, brand="smiley", color_barcode="0100", color_name="黑色（笑脸）",
            source_workbook="test", source_sheet="test", source_row_number="1", raw_payload={},
        ))
    repository = object.__new__(ProductRepository)
    repository.engine = engine
    try:
        payload = repository._prepare_record({
            "sku": "6362022365400", "color_code": "0100", "color": "棕色",
        }, brand="smiley")
        assert payload["color_code"] == "0100"
        assert payload["color"] == "黑色（笑脸）"

        suffix_payload = repository._prepare_record({
            "sku": "6362022360100", "color_code": "6362022360100", "color": "棕色",
        }, brand="smiley")
        assert suffix_payload["color_code"] == "0100"
        assert suffix_payload["color"] == "黑色（笑脸）"

        with engine.begin() as connection:
            transactional_payload = repository._prepare_record({
                "sku": "6362022365400", "color_code": "0100", "color": "棕色",
            }, brand="smiley", connection=connection)
        assert transactional_payload["color"] == "黑色（笑脸）"
    finally:
        engine.dispose()


def test_smiley_color_mapping_sync_preserves_a_different_saved_code():
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function(
        "date_trunc", 2, lambda _unit, value: value,
    ))
    COLOR_BARCODE_TABLE.create(engine)
    table = PRODUCT_ARCHIVE_TABLES["smiley"]
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(COLOR_BARCODE_TABLE.insert().values(
            id=1, brand="smiley", color_barcode="0100", color_name="黑色（笑脸）",
            source_workbook="test", source_sheet="test", source_row_number="1", raw_payload={},
        ))
        connection.execute(table.insert(), [
            {"id": 1, "sku": "SKU-5400", "color_code": "0200", "color": "黑色（笑脸）",
             "source_workbook": "test", "source_sheet": "test", "source_row_number": "1", "raw_payload": {}},
            {"id": 2, "sku": "SKU-0100", "color_code": None, "color": "黑色（笑脸）",
             "source_workbook": "test", "source_sheet": "test", "source_row_number": "2", "raw_payload": {}},
        ])
    repository = object.__new__(ProductRepository)
    repository.engine = engine
    repository._color_code_cache = {}
    try:
        result = repository.sync_color_mapping_to_products(
            source_brand="smiley", color_name="黑色（笑脸）", color_code="0100",
        )
        assert result["updated"] == 1
        repository.sync_all_color_mappings_to_products()
        with engine.connect() as connection:
            saved = {row.id: row.color_code for row in connection.execute(
                table.select().with_only_columns(table.c.id, table.c.color_code)
            )}
        assert saved == {1: "0200", 2: "0100"}
    finally:
        engine.dispose()
