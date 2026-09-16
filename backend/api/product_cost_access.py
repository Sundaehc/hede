from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request


PRODUCT_COST_RESTRICTED_DEPARTMENTS = {"客服部", "美工部"}
PRODUCT_COST_FIELD_NAMES = {
    "cost",
    "costprice",
    "costunitprice",
    "costmanualoverride",
    "gendercosts",
    "presetprice",
    "成本",
    "成本价",
    "成本单价",
    "预设售价",
    "预设售价3",
    "女码价格",
    "男码价格",
}


def _normalized_field_name(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "").replace(" ", "")


def is_product_cost_field(value: object) -> bool:
    normalized = _normalized_field_name(value)
    return (
        normalized in PRODUCT_COST_FIELD_NAMES
        or "成本" in normalized
        or normalized.startswith("预设售价")
    )


def user_can_view_product_cost(user: Mapping[str, object] | None) -> bool:
    if not user:
        return True
    if str(user.get("role_code") or "").strip() == "super_admin":
        return True
    return str(user.get("department_code") or "").strip() not in PRODUCT_COST_RESTRICTED_DEPARTMENTS


def request_can_view_product_cost(request: Request) -> bool:
    state = getattr(request, "state", None)
    user = getattr(state, "current_user", None)
    return user_can_view_product_cost(user if isinstance(user, Mapping) else None)


def redact_product_cost_data(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): redact_product_cost_data(item)
            for key, item in value.items()
            if not is_product_cost_field(key)
        }
    if isinstance(value, list):
        return [redact_product_cost_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_product_cost_data(item) for item in value]
    return value


def redact_product_cost_item(item: Mapping[str, object]) -> dict[str, object]:
    redacted = redact_product_cost_data(item)
    return dict(redacted) if isinstance(redacted, Mapping) else {}


def _redact_product_cost_summary(value: object) -> str:
    summary = str(value or "")
    separator = "：修改了 "
    if separator not in summary:
        return summary
    prefix, field_text = summary.split(separator, 1)
    fields = [field.removesuffix("等字段") for field in field_text.split("、")]
    visible_fields = [field for field in fields if not is_product_cost_field(field)]
    if not visible_fields:
        return prefix
    return f"{prefix}{separator}{'、'.join(visible_fields)}"


def redact_product_cost_log_item(item: Mapping[str, object]) -> dict[str, object]:
    result = dict(item)
    result["summary"] = _redact_product_cost_summary(result.get("summary"))
    changed_fields = result.get("changed_fields")
    if isinstance(changed_fields, list):
        result["changed_fields"] = [
            redact_product_cost_data(change)
            for change in changed_fields
            if not (
                isinstance(change, Mapping)
                and (
                    is_product_cost_field(change.get("field"))
                    or is_product_cost_field(change.get("label"))
                )
            )
        ]
    result["before_data"] = redact_product_cost_data(result.get("before_data"))
    result["after_data"] = redact_product_cost_data(result.get("after_data"))
    return result
