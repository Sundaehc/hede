from datetime import date
from typing import Literal

from fastapi import HTTPException, Query


def purchase_detail_filters(
    date_start: date | None = None,
    date_end: date | None = None,
    brands: list[str] | None = Query(None),
    supplier: str | None = None,
    warehouse: list[str] | None = Query(None),
    product_code: str | None = None,
    product_name: str | None = None,
    color_name: str | None = None,
    size_name: str | None = None,
    sort_direction: Literal["asc", "desc"] = "asc",
) -> dict[str, object]:
    if date_start and date_end and date_start > date_end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    return {
        "date_start": date_start.isoformat() if date_start else None,
        "date_end": date_end.isoformat() if date_end else None,
        "brands": brands, "supplier": supplier, "warehouse": warehouse,
        "product_code": product_code, "product_name": product_name,
        "color_name": color_name, "size_name": size_name, "sort_direction": sort_direction,
    }
