from domain.gj_brand import infer_gj_fine_table_brand, infer_supplier_brand_from_name


def test_eblan_supplier_gender_does_not_change_product_brand():
    assert infer_supplier_brand_from_name("168（伊伴女鞋）") == "eblan_womens"
    assert infer_supplier_brand_from_name("EBLAN男鞋") == "eblan"
    assert infer_gj_fine_table_brand({"primary_supplier": "168（伊伴女鞋）"}) == "eblan"


def test_ni_supplier_names_are_classified_as_ni():
    assert infer_supplier_brand_from_name("NI") == "ni"
    assert infer_supplier_brand_from_name(" ni ") == "ni"
    assert infer_supplier_brand_from_name("福德（NI）") == "ni"


def test_unrelated_supplier_names_are_not_classified_as_ni():
    assert infer_supplier_brand_from_name("NINA供应商") is None
    assert infer_supplier_brand_from_name("NI供应商") is None
    assert infer_supplier_brand_from_name("NIKE华东供应商") is None
    assert infer_supplier_brand_from_name("耐克供应商") is None
