from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re


MONTHLY_ORDER_KEY_FIELDS = (
    "internal_order_id",
    "online_order_id",
    "online_sub_order_id",
    "order_time",
    "shop_name",
    "style_code",
    "product_code",
    "quantity",
    "status",
)
MONTHLY_ORDER_SUBORDER_HEADERS = ("子订单编号", "子订单号")
MONTHLY_ORDER_KEY_PREFIX = "jst-monthly-orders:v2|"


def _key_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def monthly_order_record_key(record: Mapping[str, object]) -> str:
    values = [_key_text(record.get(field)) for field in MONTHLY_ORDER_KEY_FIELDS]
    quantity_index = MONTHLY_ORDER_KEY_FIELDS.index("quantity")
    quantity = values[quantity_index]
    if quantity:
        try:
            parsed = Decimal(quantity.replace(",", ""))
            if parsed.is_finite() and parsed == parsed.to_integral_value():
                values[quantity_index] = str(int(parsed))
        except InvalidOperation:
            pass
    raw = record.get("raw_payload")
    suborder = ""
    if isinstance(raw, Mapping):
        suborder = next((_key_text(raw.get(header)) for header in MONTHLY_ORDER_SUBORDER_HEADERS if _key_text(raw.get(header))), "")
    values.append(suborder)
    material = MONTHLY_ORDER_KEY_PREFIX + "".join(f"{len(value)}:{value}" for value in values)
    return sha256(material.encode("utf-8")).hexdigest()


def monthly_order_record_key_sql(alias: str = "orders") -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", alias):
        raise ValueError("Invalid SQL table alias")
    values = [f"btrim(coalesce({alias}.{field}::text, ''))" for field in MONTHLY_ORDER_KEY_FIELDS]
    suborders = ", ".join(
        f"nullif(btrim({alias}.raw_payload ->> '{header}'), '')"
        for header in MONTHLY_ORDER_SUBORDER_HEADERS
    )
    values.append(f"coalesce({suborders}, '')")
    material = " || ".join([f"'{MONTHLY_ORDER_KEY_PREFIX}'", *(f"length({value})::text || ':' || {value}" for value in values)])
    return f"encode(sha256(convert_to({material}, 'UTF8')), 'hex')"


def deduplicate_monthly_order_rows(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    unique: dict[tuple[object, str], dict[str, object]] = {}
    for row in rows:
        row["record_key"] = monthly_order_record_key(row)
        identity = (row.get("order_time_at"), row["record_key"])
        previous = unique.get(identity)
        if previous is not None:
            excluded = {"source_workbook", "source_sheet", "source_row_number", "record_key"}
            previous_data = {field: value for field, value in previous.items() if field not in excluded}
            current_data = {field: value for field, value in row.items() if field not in excluded}
            if previous_data != current_data:
                raise ValueError(
                    f"聚水潭订单去重键冲突：源文件第 {previous.get('source_row_number')}、"
                    f"{row.get('source_row_number')} 行业务数据不同，已取消导入"
                )
        unique[identity] = row
    return list(unique.values()), len(rows) - len(unique)
