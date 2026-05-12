from __future__ import annotations

import io
import urllib.parse

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from domain.inventory_sources import (
    DOCUMENT_TYPES,
    INVENTORY_CANONICAL_COLUMNS,
    INVENTORY_COLUMN_ALIASES,
    INVENTORY_EXPORT_LABELS,
)

router = APIRouter()

CN_TO_FIELD = {cn: en for cn, en in INVENTORY_COLUMN_ALIASES.items() if en in INVENTORY_CANONICAL_COLUMNS}


@router.get("/inventory")
def list_inventory(
    request: Request,
    date_start: str | None = None,
    date_end: str | None = None,
    supplier: str | None = None,
    product_code: str | None = None,
    warehouse: str | None = None,
    document_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    repository = request.app.state.inventory_repository
    return repository.list_records(
        date_start=date_start,
        date_end=date_end,
        supplier=supplier,
        product_code=product_code,
        warehouse=warehouse,
        document_type=document_type,
        page=page,
        page_size=page_size,
    )


@router.get("/inventory/{record_id}")
def get_inventory_record(request: Request, record_id: int):
    repository = request.app.state.inventory_repository
    record = repository.get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.post("/inventory")
def create_inventory_record(request: Request, payload: dict):
    repository = request.app.state.inventory_repository
    summary = (payload.get("summary") or "").strip()
    if summary:
        from domain.inventory_schema import INVENTORY_TABLE
        from sqlalchemy import select as sa_select
        with repository.engine.connect() as conn:
            existing = conn.execute(
                sa_select(INVENTORY_TABLE).where(INVENTORY_TABLE.c.summary == summary)
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"摘要 '{summary}' 已存在")
    return {"item": repository.create_record(payload), "message": "创建成功"}


@router.put("/inventory/{record_id}")
def update_inventory_record(request: Request, record_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    record = repository.update_record(record_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"item": record, "message": "更新成功"}


@router.delete("/inventory/{record_id}")
def delete_inventory_record(request: Request, record_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_record(record_id):
        raise HTTPException(status_code=404, detail="Record not found")
    return {"message": "删除成功"}


@router.post("/inventory/batch-delete")
def batch_delete_inventory(request: Request, payload: dict):
    ids = payload.get("ids", [])
    repository = request.app.state.inventory_repository
    deleted = repository.delete_records(ids)
    return {"deleted": deleted, "message": f"已删除 {deleted} 条记录"}


@router.post("/inventory/import")
async def import_inventory(request: Request, file: UploadFile = None):
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

    headers = [str(h).strip() if h else "" for h in header_row]

    reverse_aliases = {}
    for cn_label, en_field in CN_TO_FIELD.items():
        reverse_aliases[cn_label] = en_field
        reverse_aliases[en_field] = en_field

    known_fields = set(CN_TO_FIELD.values()) | set(CN_TO_FIELD.keys())
    repository = request.app.state.inventory_repository
    created = 0
    skipped = 0

    new_suppliers: set[str] = set()
    new_warehouses: set[str] = set()

    for row in iterator:
        row_dict = {}
        for idx, cell_value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_dict[headers[idx]] = cell_value

        payload = {}
        extra_fields = {}
        for key, value in row_dict.items():
            field = reverse_aliases.get(key)
            if field:
                str_value = str(value).strip() if value is not None else None
                # Normalize numeric fields
                if field == "quantity" and str_value:
                    try:
                        str_value = str(int(float(str_value))) if float(str_value) == int(float(str_value)) else str(float(str_value))
                    except ValueError:
                        pass
                if field == "unit_price" and str_value:
                    try:
                        str_value = str(float(str_value))
                    except ValueError:
                        pass
                payload[field] = str_value
            elif key and key not in known_fields:
                if value is not None and str(value).strip():
                    extra_fields[key] = str(value).strip()

        # Validate document_type
        doc_type = payload.get("document_type", "")
        if doc_type and doc_type not in DOCUMENT_TYPES:
            extra_fields["原始单据类型"] = doc_type
            payload["document_type"] = ""

        if not payload.get("product_code") and not payload.get("date"):
            continue

        if extra_fields:
            payload["extra_fields"] = extra_fields

        payload.setdefault("source_workbook", file.filename or "")
        payload.setdefault("source_sheet", ws.title or "")
        payload["raw_payload"] = {k: str(v) if v is not None else "" for k, v in row_dict.items()}

        supplier_name = payload.get("supplier", "").strip()
        warehouse_name = payload.get("warehouse", "").strip()
        if supplier_name:
            new_suppliers.add(supplier_name)
        if warehouse_name:
            new_warehouses.add(warehouse_name)

        try:
            repository.create_record(payload)
            created += 1
        except Exception:
            skipped += 1

    # Sync new suppliers and warehouses
    supplier_added = 0
    for name in new_suppliers:
        if not repository.get_supplier_by_name(name):
            repository.create_supplier({"name": name})
            supplier_added += 1

    warehouse_added = 0
    for name in new_warehouses:
        if not repository.get_warehouse_by_name(name):
            repository.create_warehouse({"name": name})
            warehouse_added += 1

    wb.close()
    msg = f"导入完成：新增 {created} 条记录"
    if skipped > 0:
        msg += f"，跳过 {skipped} 条重复记录"
    if supplier_added > 0:
        msg += f"，新增供应商 {supplier_added} 个"
    if warehouse_added > 0:
        msg += f"，新增仓库 {warehouse_added} 个"
    return {"created": created, "skipped": skipped, "message": msg}


@router.get("/inventory/export")
def export_inventory(request: Request):
    repository = request.app.state.inventory_repository
    result = repository.list_records(page=1, page_size=100_000)
    items = result["items"]

    wb = Workbook()
    ws = wb.active
    ws.title = "进销存数据"

    headers = [INVENTORY_EXPORT_LABELS.get(c, c) for c in INVENTORY_CANONICAL_COLUMNS]
    ws.append(headers)

    for item in items:
        row = [item.get(c) for c in INVENTORY_CANONICAL_COLUMNS]
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = urllib.parse.quote("进销存数据.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
