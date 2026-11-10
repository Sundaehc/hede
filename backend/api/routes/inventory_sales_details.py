from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from openpyxl import Workbook
from sqlalchemy import select

from api.excel_export import style_excel_workbook
from api.detail_export_selection import DetailExportSelection, ensure_selection_complete
from api.detail_report_filters import purchase_detail_filters
from api.operation_log_utils import write_operation_log
from api.routes.inventory import _excel_number, _stream_excel_workbook
from domain.inventory_schema import INVENTORY_TABLE, WAREHOUSE_TABLE
from domain.inventory_sources import normalize_document_type
from storage.inventory_repository import WHOLESALE_DOCUMENT_TYPES


router = APIRouter(prefix="/inventory-reports/sales-details", tags=["inventory"])


def sales_detail_filters(
    filters: Annotated[dict[str, object], Depends(purchase_detail_filters)],
    document_type: str | None = None,
    display_mode: Literal["goods", "barcode"] = "goods",
) -> dict[str, object]:
    document_type = normalize_document_type(document_type) if document_type else None
    if document_type and document_type not in WHOLESALE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="单据类型仅支持批发销售单或批发销售退货单")
    return {**filters, "document_type": document_type, "display_mode": display_mode}


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
    return _export_sales_details(request, filters)


@router.post("/export")
def export_selected_sales_details(request: Request, filters: DetailFilters, selection: DetailExportSelection):
    return _export_sales_details(request, filters, selection.selected_rows(str(filters.get("display_mode", "goods"))))


def _export_sales_details(request: Request, filters: dict, selected_rows: list[str] | None = None):
    result = request.app.state.inventory_repository.list_sales_details(**filters, page=1, page_size=100_000,
                                                                      **({"selected_rows": selected_rows} if selected_rows is not None else {}))
    if selected_rows is not None:
        ensure_selection_complete(selected_rows, result)
    if result["total"] > 100_000:
        raise HTTPException(status_code=400, detail="商品销售明细超过 100000 条，请缩小日期或商品筛选范围后导出")
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "商品销售明细"
    by_barcode = filters.get("display_mode") == "barcode"
    barcode_headers = ["商品编码", "颜色条码", "尺码名称", "尺码条码", "编码提示"] if by_barcode else []
    worksheet.append([
        "行号", "货号", "商品全名", "颜色名称", *barcode_headers, "单据类型", "单据编号", "日期",
        "销售数量", "销售金额", "零售金额", "单位编号", "单位全名", "仓库全名",
    ])
    for item in result["items"]:
        barcode_values = [item.get(key) or "" for key in ("barcode", "color_barcode", "size_name", "size_barcode", "barcode_issue")] if by_barcode else []
        worksheet.append([
            item["row_number"], item["product_code"] or "", item["product_name"] or "",
            item["color_name"] or "", *barcode_values, item["document_type"], item["document_number"] or "",
            item["date"] or "", _excel_number(item["sales_quantity"]), _excel_number(item["sales_amount"]),
            item["retail_amount"] or "", item["unit_code"] or "", item["unit_name"] or "", item["warehouse_name"] or "",
        ])
        if by_barcode:
            for column in range(5, 10):
                worksheet.cell(row=worksheet.max_row, column=column).data_type = "s"
    style_excel_workbook(workbook)
    exported = len(result["items"])
    write_operation_log(
        request, module="sales_detail", action="export", entity_type="sales_detail",
        entity_label="商品销售明细", summary=f"导出{'所选' if selected_rows is not None else ''}商品销售明细 {exported} 条",
        after_data={"exported_rows": exported, "filters": filters,
                    "selection": "selected" if selected_rows is not None else "all",
                    "selected_count": len(selected_rows) if selected_rows is not None else None},
    )
    return _stream_excel_workbook(workbook, "商品销售明细.xlsx")
