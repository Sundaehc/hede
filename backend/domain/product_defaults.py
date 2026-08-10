from __future__ import annotations

from collections.abc import MutableMapping


CBANNER_WOMENS_DEFAULT_GROUP_NAME = "女鞋"


def apply_product_defaults(brand_group: str, row: MutableMapping[str, object]) -> MutableMapping[str, object]:
    if brand_group == "cbanner_womens":
        group_name = row.get("group_name")
        if group_name is None or not str(group_name).strip():
            row["group_name"] = CBANNER_WOMENS_DEFAULT_GROUP_NAME
    return row
