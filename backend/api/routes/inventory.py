from __future__ import annotations

import io
import urllib.parse
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from domain.inventory_sources import (
    DOCUMENT_TYPES,
    INVENTORY_CANONICAL_COLUMNS,
    INVENTORY_COLUMN_ALIASES,
    INVENTORY_DETAIL_ALIASES,
    INVENTORY_DETAIL_COLUMNS,
    INVENTORY_EXPORT_LABELS,
)

router = APIRouter()

CN_TO_FIELD = {cn: en for cn, en in INVENTORY_COLUMN_ALIASES.items() if en in INVENTORY_CANONICAL_COLUMNS}
DETAIL_CN_TO_FIELD = {cn: en for cn, en in INVENTORY_DETAIL_ALIASES.items() if en in INVENTORY_DETAIL_COLUMNS}

EXCEL_EPOCH = datetime(1899, 12, 30)


def _normalize_date(value: str | None) -> str | None:
    """Convert Excel serial date number to YYYY-MM-DD string. Passes through non-numeric values unchanged."""
    if not value:
        return value
    try:
        serial = float(value)
        # Only treat as Excel serial if it looks like a date number (between 1 and ~100000 days from epoch)
        if 1 <= serial <= 100000:
            return (EXCEL_EPOCH + timedelta(days=int(serial))).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    return value


@router.get("/inventory")
def list_inventory(
    request: Request,
    date_start: str | None = None,
    date_end: str | None = None,
    supplier: str | None = None,
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
        warehouse=warehouse,
        document_type=document_type,
        page=page,
        page_size=page_size,
    )


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


@router.get("/inventory/ending-balance")
def get_ending_inventory(
    request: Request,
    stock_date: str,
    date_start: str | None = None,
    date_end: str | None = None,
    product_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    repository = request.app.state.inventory_repository
    settings = request.app.state.settings
    return repository.get_ending_inventory(
        jst_stock_root=settings.jst_stock_root,
        stock_date=stock_date,
        date_start=date_start,
        date_end=date_end,
        product_code=product_code,
        page=page,
        page_size=page_size,
    )


@router.post("/inventory/import-jst-stock")
def import_jst_stock(request: Request, stock_date: str | None = None):
    if stock_date is None:
        from datetime import datetime
        now = datetime.now()
        stock_date = f"{now.month:02d}.{now.day:02d}"
    repository = request.app.state.inventory_repository
    settings = request.app.state.settings
    return repository.import_jst_stock(
        jst_stock_root=settings.jst_stock_root,
        stock_date=stock_date,
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
    if payload.get("date"):
        payload["date"] = _normalize_date(str(payload["date"]))
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
    if payload.get("date"):
        payload["date"] = _normalize_date(str(payload["date"]))
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


@router.get("/inventory/{record_id}/details")
def list_inventory_details(request: Request, record_id: int):
    repository = request.app.state.inventory_repository
    return {"items": repository.list_details(record_id)}


@router.post("/inventory/{record_id}/details")
def create_inventory_detail(request: Request, record_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    payload["document_id"] = record_id
    return {"item": repository.create_detail(payload), "message": "明细添加成功"}


@router.put("/inventory/{record_id}/details/{detail_id}")
def update_inventory_detail(request: Request, record_id: int, detail_id: int, payload: dict):
    repository = request.app.state.inventory_repository
    payload["document_id"] = record_id
    detail = repository.update_detail(detail_id, payload)
    if detail is None:
        raise HTTPException(status_code=404, detail="Detail not found")
    return {"item": detail, "message": "明细更新成功"}


@router.delete("/inventory/{record_id}/details/{detail_id}")
def delete_inventory_detail(request: Request, record_id: int, detail_id: int):
    repository = request.app.state.inventory_repository
    if not repository.delete_detail(detail_id):
        raise HTTPException(status_code=404, detail="Detail not found")
    return {"message": "明细删除成功"}


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

    # Build reverse alias maps
    reverse_aliases: dict[str, str] = {}
    for cn_label, en_field in CN_TO_FIELD.items():
        reverse_aliases[cn_label] = en_field
        reverse_aliases[en_field] = en_field

    detail_reverse_aliases: dict[str, str] = {}
    for cn_label, en_field in DETAIL_CN_TO_FIELD.items():
        detail_reverse_aliases[cn_label] = en_field
        detail_reverse_aliases[en_field] = en_field

    known_fields = set(CN_TO_FIELD.values()) | set(CN_TO_FIELD.keys())
    detail_known_fields = set(DETAIL_CN_TO_FIELD.values()) | set(DETAIL_CN_TO_FIELD.keys())
    repository = request.app.state.inventory_repository

    # Phase 1: Parse all rows and group by summary
    # Each row_entry = {doc: dict, detail: dict}
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []  # preserve insertion order

    for row in iterator:
        row_dict = {}
        for idx, cell_value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_dict[headers[idx]] = cell_value

        doc_payload: dict[str, object] = {}
        detail_payload: dict[str, object] = {}
        extra_fields: dict[str, str] = {}

        for key, value in row_dict.items():
            doc_field = reverse_aliases.get(key)
            detail_field = detail_reverse_aliases.get(key)
            str_value = str(value).strip() if value is not None else None

            if doc_field:
                if doc_field in ("total_count", "amount") and str_value:
                    try:
                        str_value = str(float(str_value))
                    except ValueError:
                        pass
                if doc_field == "date":
                    str_value = _normalize_date(str_value)
                doc_payload[doc_field] = str_value
            elif detail_field:
                if detail_field == "quantity" and str_value:
                    try:
                        str_value = str(int(float(str_value))) if float(str_value) == int(float(str_value)) else str(float(str_value))
                    except ValueError:
                        pass
                if detail_field in ("amount", "unit_price") and str_value:
                    try:
                        str_value = str(float(str_value))
                    except ValueError:
                        pass
                detail_payload[detail_field] = str_value
            elif key and key not in known_fields and key not in detail_known_fields:
                if value is not None and str(value).strip():
                    extra_fields[key] = str(value).strip()

        if not doc_payload.get("date"):
            continue

        # Validate document_type
        doc_type = str(doc_payload.get("document_type") or "")
        if doc_type and doc_type not in DOCUMENT_TYPES:
            extra_fields["原始单据类型"] = doc_type
            doc_payload["document_type"] = ""

        if extra_fields:
            doc_payload["extra_fields"] = extra_fields

        doc_payload.setdefault("source_workbook", file.filename or "")
        doc_payload.setdefault("source_sheet", ws.title or "")

        # raw_payload stores the original row data
        raw_payload = {}
        for k, v in row_dict.items():
            raw_payload[k] = str(v) if v is not None else ""
        for rp_key, rp_value in raw_payload.items():
            if reverse_aliases.get(rp_key) == "date":
                raw_payload[rp_key] = _normalize_date(rp_value) or rp_value
                break
        doc_payload["raw_payload"] = raw_payload

        summary = str(doc_payload.get("summary") or "").strip()
        if summary not in groups:
            groups[summary] = []
            group_order.append(summary)
        groups[summary].append({"doc": doc_payload, "detail": detail_payload})

    wb.close()

    # Phase 2: Create documents with details grouped by summary
    new_suppliers: set[str] = set()
    new_warehouses: set[str] = set()
    created_docs = 0
    created_details = 0
    skipped_docs = 0

    from domain.inventory_schema import INVENTORY_TABLE
    from sqlalchemy import select as sa_select

    for summary in group_order:
        group_rows = groups[summary]
        first = group_rows[0]
        doc_payload = first["doc"]

        supplier_name = str(doc_payload.get("supplier") or "").strip()
        warehouse_name = str(doc_payload.get("warehouse") or "").strip()
        if supplier_name:
            new_suppliers.add(supplier_name)
        if warehouse_name:
            new_warehouses.add(warehouse_name)

        # Skip if summary already exists in database
        if summary:
            with repository.engine.connect() as conn:
                existing = conn.execute(
                    sa_select(INVENTORY_TABLE).where(INVENTORY_TABLE.c.summary == summary)
                ).first()
                if existing:
                    skipped_docs += 1
                    continue

        try:
            doc = repository.create_record(doc_payload)
            created_docs += 1
            doc_id = doc["id"]

            # Create detail rows that have a product_code
            for row in group_rows:
                detail = row["detail"]
                if detail.get("product_code"):
                    detail["document_id"] = doc_id
                    try:
                        repository.create_detail(detail)
                        created_details += 1
                    except Exception:
                        pass
        except Exception:
            skipped_docs += 1

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

    msg = f"导入完成：新增 {created_docs} 条单据，{created_details} 条明细"
    if skipped_docs > 0:
        msg += f"，跳过 {skipped_docs} 条已存在的单据"
    if supplier_added > 0:
        msg += f"，新增供应商 {supplier_added} 个"
    if warehouse_added > 0:
        msg += f"，新增仓库 {warehouse_added} 个"
    return {"created": created_docs, "details": created_details, "skipped": skipped_docs, "message": msg}
