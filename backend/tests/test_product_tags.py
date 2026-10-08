from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from domain.product_tag_generation import _apply_manual_overrides
from domain.product_tag_generation import (
    _add_exact_field_tags,
    _add_keyword_tags,
    _add_lifecycle_and_quality_tags,
)


def _generated_tags(row: dict[str, object]) -> tuple[dict[str, dict[str, object]], dict[tuple[str, int], dict[str, dict[str, object]]]]:
    definitions: dict[str, dict[str, object]] = {}
    product_tags: dict[tuple[str, int], dict[str, dict[str, object]]] = defaultdict(dict)
    _add_exact_field_tags(row, "cbanner_mens", 1, definitions, product_tags)
    _add_keyword_tags(row, "cbanner_mens", 1, definitions, product_tags)
    _add_lifecycle_and_quality_tags(row, "cbanner_mens", 1, definitions, product_tags)
    return definitions, product_tags


def test_product_tags_are_generated_from_archive_fields():
    definitions, product_tags = _generated_tags(
        {
            "category": "运动鞋",
            "season_category": "春季",
            "year": "2026年",
            "product_level": "A类",
            "upper_material": "网布",
            "lining_material": "绒里",
            "outsole_material": "EVA",
            "sole_style": "厚底",
            "fashion_elements": "拼接/轻便",
            "toe_shape": "圆头",
            "closure_type": "系带",
            "selling_points": "透气,轻便",
            "internal_height_increase": "3cm",
            "launch_date": date.today().isoformat(),
            "image_path": "products/test.jpg",
        }
    )

    names = {item["tag_name"] for item in definitions.values()}
    assert "品类：运动鞋" in names
    assert "年份：2026" in names
    assert "鞋面材质：网布" in names
    assert "透气" in names
    assert "新品（近180天上市）" in names
    assert set(product_tags[("cbanner_mens", 1)]) == set(definitions)


def test_upper_material_tags_keep_specific_leather_types():
    definitions, product_tags = _generated_tags({
        "upper_material": "牛皮+头层羊皮",
    })

    names = {item["tag_name"] for item in definitions.values()}
    assert "鞋面材质：牛皮" in names
    assert "鞋面材质：羊皮" in names
    assert "鞋面材质：头层" in names
    assert "鞋面材质：真皮" not in names
    material_tags = {
        item["tag_name"]
        for code, item in definitions.items()
        if code.startswith("archive_upper_material:")
    }
    assert material_tags == {"鞋面材质：牛皮", "鞋面材质：羊皮", "鞋面材质：头层"}


def test_material_tags_keep_other_specific_keywords():
    definitions, _ = _generated_tags({
        "upper_material": "超纤网面",
        "lining_material": "羊毛绒布里",
        "outsole_material": "TPU+EVA发泡",
    })

    names = {item["tag_name"] for item in definitions.values()}
    assert {
        "鞋面材质：超纤",
        "鞋面材质：网面",
        "内里材质：羊毛",
        "内里材质：绒",
        "内里材质：布里",
        "鞋底材质：TPU",
        "鞋底材质：EVA",
        "鞋底材质：发泡",
    } <= names
    assert "内里材质：毛" not in names
    assert "鞋底材质：PU" not in names


def test_product_tags_include_missing_archive_data_quality_tags():
    definitions, product_tags = _generated_tags(
        {
            "launch_date": "",
            "image_path": None,
            "upper_material": "",
            "category": "",
        }
    )

    assert {item["tag_name"] for item in definitions.values()} == {
        "缺图片",
        "缺上市日期",
        "缺鞋面材质",
        "缺品类",
    }
    assert len(product_tags[("cbanner_mens", 1)]) == 4


def test_new_product_window_excludes_old_launch_date():
    old_date = (date.today() - timedelta(days=181)).isoformat()
    definitions, _ = _generated_tags({"launch_date": old_date})

    assert "新品（近180天上市）" not in {item["tag_name"] for item in definitions.values()}


def test_manual_tag_overrides_are_preserved_during_rebuild():
    generated = {
        "archive_material_1": {
            "tag_code": "archive_material_1",
            "tag_name": "鞋面材质：复合材料",
            "tag_group": "材质",
            "is_active": True,
            "is_manual_override": False,
            "sort_order": 4,
        }
    }
    existing = {
        "archive_material_1": {
            "tag_name": "开发重点材质",
            "tag_group": "运营",
            "is_active": False,
            "is_manual_override": True,
            "sort_order": 20,
        }
    }

    result = _apply_manual_overrides(generated, existing)

    assert result["archive_material_1"] == {
        **generated["archive_material_1"],
        "tag_name": "开发重点材质",
        "tag_group": "运营",
        "is_active": False,
        "is_manual_override": True,
        "sort_order": 20,
    }
