from domain.schema import PRODUCT_TABLES



def test_product_tables_have_id_primary_key():
    for table in PRODUCT_TABLES.values():
        assert "id" in table.c
        assert table.c.id.primary_key is True
