"""Single JSON parameter keeps large selections below database bind limits."""
import json

from sqlalchemy import JSON, BigInteger, Text, cast, func, literal, select


def selected_detail_values(rows: list[str], dialect: str, *, ids: bool = False):
    values = list(dict.fromkeys(int(row.split(":", 1)[0]) for row in rows)) if ids else rows
    payload = literal(json.dumps(values, ensure_ascii=False))
    if dialect == "postgresql":
        entries = func.json_array_elements_text(cast(payload, JSON)).table_valued("value").alias("selected_detail_rows")
    else:
        entries = func.json_each(payload).table_valued("key", "value").alias("selected_detail_rows")
    return select(cast(entries.c.value, BigInteger if ids else Text))
