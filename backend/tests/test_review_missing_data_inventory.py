from unittest.mock import Mock

from scripts.review_missing_data import NULL_CHECKS, Review, YELLOW


def test_product_identity_null_review_excludes_non_product_lines():
    specification = next(
        item for item in NULL_CHECKS
        if item["table"] == "inventory_details" and item["column"] == "product_identity_id"
    )
    assert specification["where"] == "NULLIF(btrim(product_code), '') IS NOT NULL"
    assert specification["scope"] == "（有商品编码）"


def test_inventory_review_does_not_treat_archive_presence_as_unique_identity():
    review = Review(Mock(), 90, {})
    review.scalar = Mock(side_effect=[100, 0, 0, 0, 0, 0, 0, 265, 361, 265, 0])
    review.check_inventory()
    unresolved = next(row for row in review.rows if row["key"] == "inv.no_identity")
    non_product = next(row for row in review.rows if row["key"] == "inv.no_identity_no_code")
    matching = next(row for row in review.rows if row["key"] == "inv.matchable_no_identity")
    assert unresolved["detail"] == "265"
    assert non_product["detail"] == "361"
    assert "不需关联" in non_product["name"]
    assert matching["status"] == YELLOW
    assert "本应能匹配" not in matching["name"]
    assert "品牌冲突" in matching["note"]
    queries = [call.args[0] for call in review.scalar.call_args_list]
    assert "NULLIF(btrim(product_code), '') IS NOT NULL" in queries[7]
    assert "NULLIF(btrim(product_code), '') IS NULL" in queries[8]
