from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, insert, update

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.vip_schema import JST_PRICE_TABLE
from storage.inventory_repository import InventoryRepository
from storage import product_repository as product_repository_module
from storage.product_repository import ProductRepository, apply_jst_product_costs
from transform.rows import build_admin_record


@pytest.fixture
def repository(test_database_url: str, recreate_tables) -> ProductRepository:
    return ProductRepository(test_database_url)


def test_product_cost_lookup_uses_preset_price_for_every_brand(monkeypatch):
    calls: list[set[str]] = []

    def fake_load(_engine, codes: set[str]):
        calls.append(codes)
        return {"M-001": Decimal("88.00"), "M-002": Decimal("99.00")}

    monkeypatch.setattr(product_repository_module, "_load_jst_product_costs", fake_load)
    items = [
        {"brand": "cbanner_mens", "sku": "M-001", "original_sku": "M-001", "cost": Decimal("1.00")},
        {"brand": "smiley", "sku": "SMILEY-001", "original_sku": "M-002", "cost": Decimal("2.00")},
    ]

    apply_jst_product_costs(object(), items)

    assert calls == [{"M-001", "SMILEY-001", "M-002"}]
    assert [item["cost"] for item in items] == [Decimal("88.00"), Decimal("99.00")]


def test_smiley_color_name_variants_match_names_without_brand_suffix():
    variants = product_repository_module._color_name_variants("黑色（笑脸）")

    assert {"黑色（笑脸）", "黑色", "黑"}.issubset(variants)
    codes = product_repository_module._unique_color_codes([
        {"color_name": "黑色（笑脸）", "color_barcode": "0100"},
    ])
    assert codes["黑色"] == "0100"


def test_color_mapping_prefers_an_exact_name_when_variants_have_different_codes():
    codes = product_repository_module._unique_color_codes([
        {"color_name": "白银", "color_barcode": "564"},
        {"color_name": "白银色", "color_barcode": "H5"},
        {"color_name": "黑黄", "color_barcode": "45"},
        {"color_name": "黑黄", "color_barcode": "A2"},
    ])

    assert codes["白银"] == "564"
    assert codes["白银色"] == "H5"
    assert "黑黄" not in codes
    assert "黑黄色" not in codes


def test_color_mapping_sync_updates_all_product_archives_using_the_source_brand(
    repository: ProductRepository,
):
    created_items = {
        brand: repository.create_product(
            brand,
            build_admin_record(
                brand,
                {
                    "sku": f"COLOR-SYNC-{brand}",
                    "original_sku": f"COLOR-SYNC-{brand}",
                    "color": "同步咖色",
                    "color_code": "99",
                },
            ),
        )
        for brand in ("cbanner_mens", "yandou", "eblan")
    }

    with repository.engine.begin() as connection:
        connection.execute(insert(COLOR_BARCODE_TABLE).values(
            brand="cbanner_mens",
            color_name="同步咖色",
            color_barcode="SYNC02",
            source_workbook="test",
            source_sheet="test",
            source_row_number="1",
            raw_payload={},
        ))
        created_sync = repository.sync_color_mapping_to_products(
            source_brand="cbanner_mens",
            color_name="同步咖色",
            color_code="SYNC02",
            connection=connection,
        )
    assert created_sync["updated"] == 3
    for brand, item in created_items.items():
        product = repository.get_product(brand, item["id"])
        assert product["color"] == "同步咖色"
        assert product["color_code"] == "SYNC02"

    with repository.engine.begin() as connection:
        connection.execute(
            update(COLOR_BARCODE_TABLE)
            .where(COLOR_BARCODE_TABLE.c.brand == "cbanner_mens")
            .where(COLOR_BARCODE_TABLE.c.color_barcode == "SYNC02")
            .values(color_name="同步深咖色", color_barcode="SYNC03")
        )
        renamed_sync = repository.sync_color_mapping_to_products(
            source_brand="cbanner_mens",
            color_name="同步深咖色",
            color_code="SYNC03",
            previous_color_name="同步咖色",
            previous_color_code="SYNC02",
            sync_color_name=True,
            connection=connection,
        )
    assert renamed_sync["updated"] == 3
    for brand, item in created_items.items():
        product = repository.get_product(brand, item["id"])
        assert product["color"] == "同步深咖色"
        assert product["color_code"] == "SYNC03"

    with repository.engine.begin() as connection:
        connection.execute(
            delete(COLOR_BARCODE_TABLE)
            .where(COLOR_BARCODE_TABLE.c.brand == "cbanner_mens")
            .where(COLOR_BARCODE_TABLE.c.color_barcode == "SYNC03")
        )
        removed_sync = repository.sync_color_mapping_to_products(
            source_brand="cbanner_mens",
            color_name=None,
            color_code=None,
            previous_color_name="同步深咖色",
            previous_color_code="SYNC03",
            remove=True,
            connection=connection,
        )
    assert removed_sync["updated"] == 3
    for brand, item in created_items.items():
        product = repository.get_product(brand, item["id"])
        assert product["color"] == "同步深咖色"
        assert product["color_code"] is None


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


def test_list_products_filters_sku_and_original_sku_by_prefix(repository: ProductRepository):
    by_sku = repository.create_product(
        "cbanner_womens",
        build_admin_record("cbanner_womens", {"sku": "KT-001", "original_sku": "STYLE-001"}),
    )
    by_original_sku = repository.create_product(
        "cbanner_womens",
        build_admin_record("cbanner_womens", {"sku": "SKU-002", "original_sku": "KT-002"}),
    )
    repository.create_product(
        "cbanner_womens",
        build_admin_record("cbanner_womens", {"sku": "SKU-KT-003", "original_sku": "STYLE-003"}),
    )

    result = repository.list_products(
        "cbanner_womens",
        query=None,
        sku_prefix="kt",
        page=1,
        page_size=10,
    )

    assert result["total"] == 2
    assert {item["id"] for item in result["items"]} == {by_sku["id"], by_original_sku["id"]}


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


def test_sync_costs_uses_latest_combined_footwear_preset_price(repository: ProductRepository):
    product = repository.create_product(
        "cbanner_mens",
        build_admin_record(
            "cbanner_mens",
            {"sku": "COST-001", "original_sku": "COST-001", "cost": "30.00"},
        ),
    )
    with repository.engine.begin() as connection:
        connection.execute(
            JST_PRICE_TABLE.insert(),
            [
                {
                    "source_date": "2026-08-01",
                    "source_date_value": date(2026, 8, 1),
                    "source_workbook": "男女鞋合并物价信息",
                    "source_sheet": "Sheet1",
                    "source_row_number": "5",
                    "goods_code": "COST-001",
                    "goods_full_name": "测试商品",
                    "cost_unit_price": Decimal("31.00"),
                    "preset_price": Decimal("31.50"),
                },
                {
                    "source_date": "2026-08-04",
                    "source_date_value": date(2026, 8, 4),
                    "source_workbook": "男女鞋合并物价信息",
                    "source_sheet": "Sheet1",
                    "source_row_number": "5",
                    "goods_code": "COST-001",
                    "goods_full_name": "测试商品",
                    "cost_unit_price": Decimal("32.50"),
                    "preset_price": Decimal("33.00"),
                },
                {
                    "source_date": "2026-08-05",
                    "source_date_value": date(2026, 8, 5),
                    "source_workbook": "男鞋物价信息",
                    "source_sheet": "Sheet1",
                    "source_row_number": "5",
                    "goods_code": "COST-001",
                    "goods_full_name": "测试商品",
                    "cost_unit_price": Decimal("99.00"),
                    "preset_price": Decimal("99.00"),
                },
            ],
        )

    result = repository.sync_costs_from_latest_combined_footwear_price()

    assert result["updated"] == 1
    assert result["brands"]["cbanner_mens"] == {"matched": 1, "updated": 1}
    assert repository.get_product("cbanner_mens", product["id"])["cost"] == Decimal("33.00")


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


def test_delete_product_moves_row_to_recycle_bin_and_can_restore_or_purge(repository: ProductRepository):
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

    recycled = repository.list_recycled_products(brand="cbanner_womens", page=1, page_size=10)
    assert recycled["total"] == 1
    assert recycled["items"][0]["id"] == created["id"]
    assert recycled["items"][0]["deleted_at"] is not None

    restored = repository.restore_product("cbanner_womens", created["id"])
    assert restored is not None
    assert repository.get_product("cbanner_womens", created["id"]) is not None
    assert repository.list_recycled_products(brand="cbanner_womens", page=1, page_size=10)["total"] == 0

    assert repository.delete_product("cbanner_womens", created["id"]) is True
    purged = repository.permanently_delete_product("cbanner_womens", created["id"])
    assert purged is not None
    assert repository.list_recycled_products(brand="cbanner_womens", page=1, page_size=10)["total"] == 0


def test_product_recycle_bin_purges_rows_older_than_ten_days(repository: ProductRepository):
    created = repository.create_product(
        "cbanner_womens",
        build_admin_record("cbanner_womens", {"sku": "PURGE-10-DAYS", "original_sku": "PURGE-10-DAYS"}),
    )
    assert repository.delete_product("cbanner_womens", created["id"]) is True

    table = repository._table_for_brand("cbanner_womens")
    expired_at = datetime.now(timezone.utc) - timedelta(days=11)
    with repository.engine.begin() as connection:
        connection.execute(
            update(table)
            .where(table.c.id == created["id"])
            .values(deleted_at=expired_at)
        )

    result = repository.purge_expired_deleted_products()

    assert result["cbanner_womens"] == 1
    assert repository.permanently_delete_product("cbanner_womens", created["id"]) is None


def test_manual_brand_creates_independent_product_archive(repository: ProductRepository, test_database_url: str):
    inventory_repository = InventoryRepository(test_database_url)
    inventory_repository.create_tables()
    manual_brand = inventory_repository.create_supplier_brand({"name": "NS"})
    repository.ensure_manual_product_archive(manual_brand)

    assert repository.is_product_archive_brand(manual_brand["code"])
    created = repository.create_product(
        str(manual_brand["code"]),
        build_admin_record(
            str(manual_brand["code"]),
            {"sku": "NS-001", "original_sku": "NS-001", "cost": "123.45"},
        ),
    )

    assert repository.list_products(str(manual_brand["code"]), query=None, page=1, page_size=10)["items"][0]["sku"] == "NS-001"
    assert created["cost"] == Decimal("123.45")
