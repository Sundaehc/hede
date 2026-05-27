from __future__ import annotations

from decimal import Decimal

import pytest

from storage.product_repository import ProductRepository
from transform.rows import build_admin_record


@pytest.fixture
def repository(test_database_url: str) -> ProductRepository:
    return ProductRepository(test_database_url)


def test_list_products_returns_paginated_items_filtered_by_original_sku_in_desc_id_order(
    repository: ProductRepository,
):
    first = repository.create_product(
        "cbanner_womens",
        build_admin_record(
            "cbanner_womens",
            {"sku": "SKU-001", "original_sku": "Alpha-001", "color": "Black"},
        ),
    )
    second = repository.create_product(
        "cbanner_womens",
        build_admin_record(
            "cbanner_womens",
            {"sku": "SKU-002", "original_sku": "beta-002", "color": "White"},
        ),
    )
    third = repository.create_product(
        "cbanner_womens",
        build_admin_record(
            "cbanner_womens",
            {"sku": "SKU-003", "original_sku": "ALPHA-003", "color": "Red"},
        ),
    )

    page_one = repository.list_products("cbanner_womens", query="alpha", page=1, page_size=1)
    page_two = repository.list_products("cbanner_womens", query="alpha", page=2, page_size=1)

    assert page_one == {
        "items": [third],
        "total": 2,
        "page": 1,
        "page_size": 1,
    }
    assert page_two == {
        "items": [first],
        "total": 2,
        "page": 2,
        "page_size": 1,
    }
    assert second["id"] not in [item["id"] for item in page_one["items"] + page_two["items"]]


def test_list_products_treats_none_and_empty_query_as_unfiltered(repository: ProductRepository):
    first = repository.create_product(
        "cbanner_womens",
        build_admin_record(
            "cbanner_womens",
            {"sku": "SKU-001", "original_sku": "Alpha-001"},
        ),
    )
    second = repository.create_product(
        "cbanner_womens",
        build_admin_record(
            "cbanner_womens",
            {"sku": "SKU-002", "original_sku": "Beta-002"},
        ),
    )

    expected = {
        "items": [second, first],
        "total": 2,
        "page": 1,
        "page_size": 10,
    }

    assert repository.list_products("cbanner_womens", query=None, page=1, page_size=10) == expected
    assert repository.list_products("cbanner_womens", query="", page=1, page_size=10) == expected


def test_get_product_returns_row_or_none(repository: ProductRepository):
    created = repository.create_product(
        "yandou",
        build_admin_record(
            "yandou",
            {"sku": "YA-100", "original_sku": "YA-100", "cost": "12.50"},
        ),
    )

    assert repository.get_product("yandou", created["id"]) == created
    assert repository.get_product("yandou", created["id"] + 1) is None


def test_create_product_persists_and_returns_created_row(repository: ProductRepository):
    created = repository.create_product(
        "eblan",
        build_admin_record(
            "eblan",
            {"sku": "YB-100", "original_sku": "YB-ORIG-100", "cost": "88.00"},
        ),
    )

    assert created["id"] > 0
    assert created["sku"] == "YB-100"
    assert created["original_sku"] == "YB-ORIG-100"
    assert created["cost"] == Decimal("88.00")
    assert created["source_workbook"] == "manual_admin"
    assert repository.get_product("eblan", created["id"]) == created


def test_update_product_returns_updated_row_and_none_for_missing_record(
    repository: ProductRepository,
):
    created = repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {"sku": "QM-100", "original_sku": "QM-ORIG-100", "color": "Black"},
        ),
    )

    updated = repository.update_product(
        "cbanner_mens",
        created["id"],
        build_admin_record(
            "cbanner_mens",
            {"sku": "QM-100-NEW", "original_sku": "QM-ORIG-100", "color": "Brown"},
            existing_metadata={
                "source_workbook": created["source_workbook"],
                "source_sheet": created["source_sheet"],
                "source_row_number": created["source_row_number"],
            },
        ),
    )

    assert updated is not None
    assert updated["id"] == created["id"]
    assert updated["sku"] == "QM-100-NEW"
    assert updated["color"] == "Brown"
    assert updated["source_workbook"] == created["source_workbook"]
    assert repository.update_product("cbanner_mens", created["id"] + 9999, {"sku": "missing"}) is None


def test_delete_product_removes_row_and_reports_success(repository: ProductRepository):
    created = repository.create_product(
        "cbanner_womens",
        build_admin_record(
            "cbanner_womens",
            {"sku": "DEL-1", "original_sku": "DEL-1"},
        ),
    )

    assert repository.delete_product("cbanner_womens", created["id"]) is True
    assert repository.get_product("cbanner_womens", created["id"]) is None
    assert repository.delete_product("cbanner_womens", created["id"]) is False
