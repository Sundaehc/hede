from __future__ import annotations

from pipeline.import_pipeline import _resolve_size_range


def test_product_size_group_mapping_takes_priority_over_source_size_range() -> None:
    assert _resolve_size_range(
        {"C5563406D80": "女鞋定制尺码组"},
        "管家婆尺码段",
        "C5563406D80",
    ) == "女鞋定制尺码组"


def test_product_size_group_sync_keeps_source_size_range_without_mapping() -> None:
    assert _resolve_size_range({}, "管家婆尺码段", "C5563406D80") == "管家婆尺码段"
