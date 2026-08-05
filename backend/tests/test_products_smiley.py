from api.schemas import ProductWriteRequest
from domain.schema import PRODUCT_ARCHIVE_TABLES, PRODUCT_TABLES
from pipeline.import_pipeline import GJ_PRODUCT_BRANDS


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
