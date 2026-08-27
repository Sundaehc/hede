from api.routes.product_auxiliary_attributes import (
    _build_auxiliary_attribute_export_workbook,
)


def test_auxiliary_attribute_export_contains_only_type_and_value_columns():
    workbook = _build_auxiliary_attribute_export_workbook(
        [
            {"attribute_type": "鞋面材质", "attribute_name": "牛皮革"},
            {"attribute_type": "执行标准", "attribute_name": "企业标准"},
        ]
    )

    rows = list(workbook.active.values)

    assert rows == [
        ("属性类型", "属性值"),
        ("鞋面材质", "牛皮革"),
        ("执行标准", "企业标准"),
    ]
