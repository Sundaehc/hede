from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from api.routes.images import image_url_for
from domain.sources import CANONICAL_COLUMNS, COLUMN_ALIASES
from transform.rows import build_admin_record

router = APIRouter()

EXPORT_LABELS = {
    "image_path": "图片",
    "sku": "货号",
    "original_sku": "原始货号",
    "group_name": "组别",
    "cost": "成本",
    "factory_sku": "工厂货号",
    "color": "颜色",
    "season_category": "季节分类",
    "year": "年份",
    "upper_material": "鞋面材质",
    "lining_material": "内里材质",
    "outsole_material": "大底材质",
    "insole_material": "鞋垫材质",
    "execution_standard": "执行标准",
    "heel_height": "跟高",
    "shoe_width": "鞋宽",
    "shoe_length": "鞋长",
    "shaft_circumference": "筒围",
    "shaft_height": "筒高",
    "internal_height_increase": "内增高",
    "internal_height_note": "内增高备注",
    "upper_height": "鞋帮",
    "toe_shape": "鞋头款式",
    "closure_type": "闭合方式",
    "shoe_box_spec": "鞋盒规格",
    "first_order_time": "首单时间",
}

EXPORT_COLUMNS = [c for c in CANONICAL_COLUMNS if c != "image_path"]
IMPORT_ALIAS_TO_FIELD = {v: k for k, v in COLUMN_ALIASES.items() if v in EXPORT_COLUMNS}


@router.get("/export")
def export_products(
    request: Request,
    brand: str = Query(...),
):
    repository = request.app.state.repository

    table = repository.list_products(brand, query=None, page=1, page_size=1_000_000)
    items = table["items"]

    wb = Workbook()
    ws = wb.active
    ws.title = "商品数据"

    headers = [EXPORT_LABELS.get(c, c) for c in EXPORT_COLUMNS]
    ws.append(headers)

    for item in items:
        row = [item.get(c) for c in EXPORT_COLUMNS]
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    brand_label = brand
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={brand_label}_products.xlsx"},
    )


@router.post("/import")
async def import_products(
    request: Request,
    brand: str = Query(...),
    file: UploadFile = None,
):
    if file is None:
        raise HTTPException(status_code=400, detail="No file uploaded")

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Excel file")

    ws = wb.active
    iterator = ws.iter_rows(values_only=True)
    header_row = next(iterator, None)
    if header_row is None:
        wb.close()
        raise HTTPException(status_code=400, detail="Empty file")

    from transform.rows import normalize_header

    headers = [normalize_header(h) for h in header_row]

    reverse_aliases = {}
    for cn_label, en_field in IMPORT_ALIAS_TO_FIELD.items():
        reverse_aliases[cn_label] = en_field
        reverse_aliases[en_field] = en_field

    repository = request.app.state.repository
    created = 0
    updated = 0

    for row in iterator:
        row_dict = {}
        for idx, cell_value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_dict[headers[idx]] = cell_value

        payload = {}
        for key, value in row_dict.items():
            field = reverse_aliases.get(key)
            if field:
                payload[field] = value

        if not payload.get("original_sku") and not payload.get("sku"):
            continue

        if payload.get("original_sku") and not payload.get("sku"):
            payload["sku"] = payload["original_sku"]
        elif payload.get("sku") and not payload.get("original_sku"):
            payload["original_sku"] = payload["sku"]

        existing = repository.find_by_original_sku(brand, payload["original_sku"])
        record = build_admin_record(brand, payload)
        if existing is not None:
            for meta_key in ("source_workbook", "source_sheet", "source_row_number"):
                record[meta_key] = existing[meta_key]
            repository.update_product(brand, existing["id"], record)
            updated += 1
        else:
            repository.create_product(brand, record)
            created += 1

    wb.close()
    return {"created": created, "updated": updated, "message": f"导入完成：新增 {created} 条，更新 {updated} 条"}
