from api.product_goods_cache import (
    clear_product_goods_cache,
    get_product_goods_cache,
    get_product_goods_risk_codes_cache,
    set_product_goods_cache,
    set_product_goods_risk_codes_cache,
)


def test_product_goods_cache_returns_payload_for_same_key():
    key = ("cbanner_womens", "", "", "", "", 1, 50)
    payload = {"items": [{"id": 1}]}

    clear_product_goods_cache()
    set_product_goods_cache(key, payload)

    assert get_product_goods_cache(key) == payload


def test_product_goods_cache_clear_removes_payloads():
    key = ("cbanner_womens", "", "", "", "", 1, 50)

    set_product_goods_cache(key, {"items": []})
    clear_product_goods_cache()

    assert get_product_goods_cache(key) is None


def test_product_goods_cache_clear_removes_risk_product_codes():
    clear_product_goods_cache()
    set_product_goods_risk_codes_cache("cbanner_mens", {"A100", "A101"})

    assert get_product_goods_risk_codes_cache("cbanner_mens") == ("A100", "A101")

    clear_product_goods_cache()

    assert get_product_goods_risk_codes_cache("cbanner_mens") is None
