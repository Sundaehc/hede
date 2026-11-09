from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from openpyxl import Workbook
from sqlalchemy import select

from api.excel_export import style_excel_workbook
from api.operation_log_utils import write_operation_log
from api.routes.inventory import _excel_number, _stream_excel_workbook
from api.routes.purchase_order_details import purchase_detail_filters
from domain.inventory_schema import INVENTORY_TABLE, WAREHOUSE_TABLE
from domain.inventory_sources import normalize_document_type
from storage.inventory_repository import WHOLESALE_DOCUMENT_TYPES


router = APIRouter(prefix="/inventory-reports/sales-details", tags=["inventory"])


def sales_detail_filters(
    filters: Annotated[dict[str, object], Depends(purchase_detail_filters)],
    document_type: str | None = None,
) -> dict[str, object]:
    document_type = normalize_document_type(document_type) if document_type else None
    if document_type and document_type not in WHOLESALE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="单据类型仅支持批发销售单或批发销售退货单")
    return {**filters, "document_type": document_type}


DetailFilters = Annotated[dict[str, object], Depends(sales_detail_filters)]


@router.get("")
def list_sales_details(
    request: Request, filters: DetailFilters,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
):
    return request.app.state.inventory_repository.list_sales_details(**filters, page=page, page_size=page_size)


@router.get("/options")
def sales_detail_options(request: Request):
    repository = request.app.state.inventory_repository
    with repository.engine.connect() as connection:
        # Include historical sales customer names as well as current customers.
        customers = connection.execute(select(INVENTORY_TABLE.c.supplier).where(
            INVENTORY_TABLE.c.deleted_at.is_(None),
            INVENTORY_TABLE.c.document_type.in_(WHOLESALE_DOCUMENT_TYPES),
            INVENTORY_TABLE.c.supplier.is_not(None), INVENTORY_TABLE.c.supplier != "",
        ).distinct().order_by(INVENTORY_TABLE.c.supplier)).scalars().all()
        warehouses = connection.execute(select(
            WAREHOUSE_TABLE.c.name, WAREHOUSE_TABLE.c.brand,
        ).order_by(WAREHOUSE_TABLE.c.name)).mappings().all()
    return {
        "brands": repository.list_inventory_brand_options(),
        "customers": [{"name": name} for name in customers],
        "warehouses": [dict(row) for row in warehouses],
    }


@router.get("/export")
def export_sales_details(request: Request, filters: DetailFilters):
    result = request.app.state.inventory_repository.list_sales_details(**filters, page=1, page_size=100_000)
    if result["total"] > 100_000:
        raise HTTPException(status_code=400, detail="商品销售明细超过 100000 条，请缩小日期或商品筛选范围后导出")
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "商品销售明细"
    worksheet.append([
        "行号", "货号", "商品全名", "颜色名称", "单据类型", "单据编号", "日期",
        "销售数量", "销售金额", "零售金额", "单位编号", "单位全名", "仓库全名",
    ])
    for item in result["items"]:
        worksheet.append([
            item["row_number"], item["product_code"] or "", item["product_name"] or "",
            item["color_name"] or "", item["document_type"], item["document_number"] or "",
            item["date"] or "", _excel_number(item["sales_quantity"]), _excel_number(item["sales_amount"]),
            item["retail_amount"] or "", item["unit_code"] or "", item["unit_name"] or "", item["warehouse_name"] or "",
        ])
    style_excel_workbook(workbook)
    exported = len(result["items"])
    write_operation_log(
        request, module="sales_detail", action="export", entity_type="sales_detail",
        entity_label="商品销售明细", summary=f"导出商品销售明细 {exported} 条",
        after_data={"exported_rows": exported, "filters": filters},
    )
    return _stream_excel_workbook(workbook, "商品销售明细.xlsx")
