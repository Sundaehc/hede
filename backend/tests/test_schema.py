from domain.schema import PRODUCT_TABLES
from domain.vip_schema import VIP_DAILY_TABLE



def test_product_tables_have_id_primary_key():
    for table in PRODUCT_TABLES.values():
        assert "id" in table.c
        assert table.c.id.primary_key is True


def test_vip_daily_uniqueness_includes_report_date():
    constraints = [
        constraint
        for constraint in VIP_DAILY_TABLE.constraints
        if getattr(constraint, "name", None) == "uq_daily_report_goods_date"
    ]

    assert len(constraints) == 1
    assert [column.name for column in constraints[0].columns] == [
        "report_type",
        "period",
        "goods_id",
        "date",
    ]
