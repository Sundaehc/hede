import pytest
from sqlalchemy import MetaData, create_engine, event, select

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES, build_product_archive_table
from storage.product_repository import ProductRepository, _unique_color_codes


def test_unique_color_codes_keeps_only_unambiguous_color_names():
    result = _unique_color_codes([
        {"color_name": "黑色", "color_barcode": "01"},
        {"color_name": "白色", "color_barcode": "02"},
        {"color_name": "白色", "color_barcode": "03"},
        {"color_name": "", "color_barcode": "04"},
    ])

    assert result == {"黑色": "01"}


@pytest.mark.parametrize("color_code", [None, "", "NS-MANUAL"])
def test_ns_product_write_never_matches_a_color_code(monkeypatch, color_code):
    repository = object.__new__(ProductRepository)

    def unexpected_lookup(_brand):
        pytest.fail("NS must not look up a color code")

    monkeypatch.setattr(repository, "_color_codes_for_brand", unexpected_lookup)
    payload = repository._prepare_record({"sku": "NS-001", "color": "黑色", "color_code": color_code}, brand="ns")
    assert payload["color_code"] == color_code
    assert payload["color"] == "黑色"


def test_ns_color_lookup_does_not_access_the_database():
    repository = object.__new__(ProductRepository)
    assert repository._color_codes_for_brand("ns") == {}


@pytest.fixture
def color_repository(monkeypatch):
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda connection, _record: connection.create_function("date_trunc", 2, lambda _unit, value: value))
    tables = {
        "ns": build_product_archive_table("manual_product_archive_31", metadata=MetaData()),
        "custom": build_product_archive_table("manual_product_archive_32", metadata=MetaData()),
        "cbanner_mens": PRODUCT_ARCHIVE_TABLES["cbanner_mens"],
        "yandou": PRODUCT_ARCHIVE_TABLES["yandou"],
        "eblan": PRODUCT_ARCHIVE_TABLES["eblan"],
    }
    COLOR_BARCODE_TABLE.create(engine)
    for table in tables.values():
        table.create(engine)
    with engine.begin() as connection:
        for mapping_id, brand, code in [(1, "ns", "NS01"), (2, "custom", "C01"), (3, "cbanner_mens", "01")]:
            connection.execute(COLOR_BARCODE_TABLE.insert().values(id=mapping_id, brand=brand, color_name="黑色", color_barcode=code, source_workbook="test", source_sheet="test", source_row_number="1", raw_payload={}))
        for brand, table in tables.items():
            connection.execute(table.insert().values(id=1, sku=f"{brand}-001", color="黑色", color_code=None, source_workbook="test", source_sheet="test", source_row_number="1", raw_payload={}))
        connection.execute(tables["ns"].insert(), [
            {"id": 2, "sku": "NS-MANUAL", "color": "黑色", "color_code": "NS-MANUAL", "source_workbook": "test", "source_sheet": "test", "source_row_number": "2", "raw_payload": {}},
            {"id": 3, "sku": "NS-LINKED", "color": "黑色", "color_code": "NS01", "source_workbook": "test", "source_sheet": "test", "source_row_number": "3", "raw_payload": {}},
        ])
    repository = object.__new__(ProductRepository)
    repository.engine = engine
    repository._color_code_cache = {}
    monkeypatch.setattr(repository, "_table_for_brand", lambda brand: tables[brand])
    monkeypatch.setattr(repository, "is_product_archive_brand", lambda brand: brand in tables)
    try:
        yield repository, tables
    finally:
        engine.dispose()


@pytest.mark.parametrize("changes", [{}, {"previous_color_name": "黑色", "previous_color_code": "NS01", "sync_color_name": True}, {"previous_color_name": "黑色", "previous_color_code": "NS01", "remove": True}])
def test_ns_mapping_changes_do_not_modify_product_color_codes(color_repository, changes):
    repository, tables = color_repository
    result = repository.sync_color_mapping_to_products(source_brand="ns", color_name="白色", color_code="NS02", **changes)
    assert result["updated"] == 0
    with repository.engine.connect() as connection:
        rows = connection.execute(select(tables["ns"].c.color, tables["ns"].c.color_code).order_by(tables["ns"].c.id)).all()
    assert rows == [("黑色", None), ("黑色", "NS-MANUAL"), ("黑色", "NS01")]


def test_bulk_color_sync_skips_ns_but_keeps_other_brands_matching(color_repository):
    repository, tables = color_repository
    result = repository.sync_all_color_mappings_to_products()
    assert result["brands"]["ns"]["updated"] == 0
    assert result["brands"]["custom"]["updated"] == 1
    assert result["brands"]["cbanner_mens"]["brands"] == {"cbanner_mens": 1, "yandou": 1, "eblan": 1}
    with repository.engine.connect() as connection:
        assert connection.execute(select(tables["ns"].c.color_code).order_by(tables["ns"].c.id)).scalars().all() == [None, "NS-MANUAL", "NS01"]
        assert connection.execute(select(tables["custom"].c.color_code)).scalar_one() == "C01"
        assert connection.execute(select(tables["cbanner_mens"].c.color_code)).scalar_one() == "01"
