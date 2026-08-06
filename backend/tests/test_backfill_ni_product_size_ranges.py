from __future__ import annotations

from scripts.backfill_ni_product_size_ranges import _group_name_for_new_ni_size_range, _prefer_ni_group_name, _size_labels


def test_ni_size_range_parser_keeps_regular_and_combined_sizes() -> None:
    assert _size_labels("35、36、37") == ("35", "36", "37")
    assert _size_labels("35-36、37-38") == ("35-36", "37-38")


def test_ni_size_range_prefers_an_ni_specific_group() -> None:
    assert _prefer_ni_group_name(["笑脸女鞋35-40", "NI尺码段35-40"]) == "NI尺码段35-40"
    assert _group_name_for_new_ni_size_range("35-45", ("35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "45")) == "NI尺码段35-45"
