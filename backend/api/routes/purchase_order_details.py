from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from openpyxl import Workbook
from sqlalchemy import select

from api.excel_export import style_excel_workbook
from api.detail_export_selection import DetailExportSelection, ensure_selection_complete
from api.detail_report_filters import purchase_detail_filters
from api.operation_log_utils import write_operation_log
from api.routes.inventory import _excel_number, _stream_excel_workbook
from domain.inventory_schema import SUPPLIER_TABLE, WAREHOUSE_TABLE


router = APIRouter(prefix="/purchase-order-details", tags=["purchase"])


DetailFilters = Annotated[dict[str, object], Depends(purchase_detail_filters)]


@router.get("")
def list_purchase_order_details(
    request: Request,
    filters: DetailFilters,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    return request.app.state.inventory_repository.list_purchase_order_details(
        **filters, page=page, page_size=page_size,
    )


@router.get("/options")
def purchase_order_detail_options(request: Request):
    repository = request.app.state.inventory_repository
    # Purchase viewers need filter options, not inventory balances or management access.
    with repository.engine.connect() as connection:
        suppliers = connection.execute(select(
            SUPPLIER_TABLE.c.name, SUPPLIER_TABLE.c.factory_code,
        ).order_by(SUPPLIER_TABLE.c.name)).mappings().all()
        warehouses = connection.execute(select(
            WAREHOUSE_TABLE.c.name, WAREHOUSE_TABLE.c.brand,
        ).order_by(WAREHOUSE_TABLE.c.name)).mappings().all()
    return {
        "brands": repository.list_inventory_brand_options(),
        "suppliers": [dict(row) for row in suppliers],
        "warehouses": [dict(row) for row in warehouses],
    }


@router.get("/export")
def export_purchase_order_details(request: Request, filters: DetailFilters):
    return _export_purchase_order_details(request, filters)


@router.post("/export")
def export_selected_purchase_order_details(request: Request, filters: DetailFilters, selection: DetailExportSelection):
    return _export_purchase_order_details(request, filters, selection.selected_rows())


def _export_purchase_order_details(request: Request, filters: dict, selected_rows: list[str] | None = None):
    repository = request.app.state.inventory_repository
    result = repository.list_purchase_order_details(**filters, page=1, page_size=100_001,
                                                   **({"selected_rows": selected_rows} if selected_rows is not None else {}))
    if selected_rows is not None:
        ensure_selection_complete(selected_rows, result)
    # Refuse an oversized export explicitly rather than silently truncating it.
    if result["total"] > 100_000:
        raise HTTPException(status_code=400, detail="采购明细超过 100000 条，请缩小日期或商品筛选范围后导出")
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "采购明细"
    worksheet.append([
        "行号", "货号", "商品全名", "颜色名称", "尺码及数量", "单据类型", "单据编号", "日期",
        "采购数量", "采购金额", "采购单价", "单位编号", "单位全名", "仓库全名",
    ])
    exported = 0
    for item in result["items"]:
        exported += 1
        sizes = "；".join(f"{size}: {quantity}" for size, quantity in item["size_quantities"].items())
        worksheet.append([
            exported, item["product_code"] or "", item["product_name"] or "",
            item["color_name"] or "", sizes, item["document_type"], item["document_number"] or "",
            item["date"] or "", _excel_number(item["purchase_quantity"]),
            _excel_number(item["purchase_amount"]), _excel_number(item["unit_price"]),
            item["unit_code"], item["unit_name"] or "", item["warehouse_name"] or "",
        ])
    style_excel_workbook(workbook)
    write_operation_log(
        request, module="purchase_order_detail", action="export", entity_type="purchase_order_detail",
        entity_label="采购明细", summary=f"导出{'所选' if selected_rows is not None else ''}采购明细 {exported} 条",
        after_data={"exported_rows": exported, "filters": filters,
                    "selection": "selected" if selected_rows is not None else "all",
                    "selected_count": len(selected_rows) if selected_rows is not None else None},
    )
    return _stream_excel_workbook(workbook, "采购明细.xlsx")
