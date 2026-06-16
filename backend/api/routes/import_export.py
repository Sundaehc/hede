from __future__ import annotations

import io
import urllib.parse

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from api.fine_table_cache import clear_fine_table_cache
from api.routes.images import image_url_for
from domain.excluded_skus import is_excluded_sku
from domain.sources import CANONICAL_COLUMNS, COLUMN_ALIASES, TABLE_NAMES
from transform.rows import build_admin_record, normalize_admin_field

router = APIRouter()

EXPORT_LABELS = {
    "image_path": "图片",
    "sku": "货号",
    "original_sku": "原始货号",
    "group_name": "组别",
    "product_level": "商品等级",
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
    "size_range": "尺码段",
    "product_model": "产品型号",
    "supplier_name": "供应商名",
    "color_code": "颜色代码",
    "launch_date": "上市时间",
}

EXPORT_COLUMNS = [c for c in CANONICAL_COLUMNS if c != "image_path"]
CN_TO_FIELD = {cn: en for cn, en in COLUMN_ALIASES.items() if en in EXPORT_COLUMNS}


@router.get("/export")
def export_products(
    request: Request,
    brand: str = Query(...),
    ids: str | None = Query(None),
):
    repository = request.app.state.repository

    if ids:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
        items = repository.get_products_by_ids(brand, id_list)
    else:
        table = repository.list_products(brand, query=None, page=1, page_size=1_000_000)
        items = table["items"]

    BRAND_LABELS = {
        "cbanner_mens": "千百度男鞋",
        "cbanner_womens": "千百度女鞋",
        "yandou": "烟斗",
        "eblan": "伊伴",
    }

    wb = Workbook()
    ws = wb.active
    ws.title = BRAND_LABELS.get(brand, brand)

    headers = [EXPORT_LABELS.get(c, c) for c in EXPORT_COLUMNS]
    ws.append(headers)

    for item in items:
        row = [item.get(c) for c in EXPORT_COLUMNS]
        ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    brand_label = BRAND_LABELS.get(brand, brand)
    filename = urllib.parse.quote(f"{brand_label}.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
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
    for cn_label, en_field in CN_TO_FIELD.items():
        reverse_aliases[cn_label] = en_field
        reverse_aliases[en_field] = en_field

    repository = request.app.state.repository
    image_matcher = request.app.state.image_matchers.get(brand)
    created = 0
    updated = 0
    imported_skus: list[str] = []

    for row in iterator:
        row_dict = {}
        for idx, cell_value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_dict[headers[idx]] = cell_value

        payload = {}
        extra_fields = {}
        known_fields = set(CN_TO_FIELD.values()) | set(CN_TO_FIELD.keys())
        for key, value in row_dict.items():
            field = reverse_aliases.get(key)
            if field:
                payload[field] = value
            elif key and key not in known_fields:
                # Unrecognized column -> store in extra_fields
                normalized = normalize_admin_field(key, value)
                if normalized is not None and str(normalized).strip():
                    extra_fields[key] = normalized

        # Normalize sku/original_sku: handle numeric values from Excel
        raw_sku = payload.get("sku")
        if raw_sku is not None:
            if isinstance(raw_sku, float) and raw_sku.is_integer():
                payload["sku"] = str(int(raw_sku))
            else:
                payload["sku"] = str(raw_sku).strip()

        raw_orig = payload.get("original_sku")
        if raw_orig is not None:
            if isinstance(raw_orig, float) and raw_orig.is_integer():
                payload["original_sku"] = str(int(raw_orig))
            else:
                payload["original_sku"] = str(raw_orig).strip()

        if not payload.get("original_sku") and not payload.get("sku"):
            continue

        if payload.get("original_sku") and not payload.get("sku"):
            payload["sku"] = payload["original_sku"]

        if is_excluded_sku(payload.get("sku"), payload.get("original_sku")):
            continue

        if extra_fields:
            payload["extra_fields"] = extra_fields

        # Match by sku only
        sku_val = str(payload.get("sku", "") or "").strip()
        existing = repository.find_by_sku(brand, sku_val) if sku_val else None

        if sku_val:
            imported_skus.append(sku_val)

        # Only keep fields that have a value in the imported row
        import_fields = {}
        for key, value in payload.items():
            if key in ("sku", "extra_fields"):
                continue
            normalized = normalize_admin_field(key, value)
            if normalized is not None and str(normalized).strip():
                import_fields[key] = normalized

        # Look up image by original_sku or sku
        if image_matcher and not import_fields.get("image_path"):
            orig_val = str(payload.get("original_sku", "") or "").strip()
            sku_val_img = str(payload.get("sku", "") or "").strip()
            found_path = None
            if orig_val:
                found_path = image_matcher.find(orig_val)
            if not found_path and sku_val_img:
                found_path = image_matcher.find(sku_val_img)
            if found_path:
                import_fields["image_path"] = found_path

        if existing is not None:
            # Merge: only overwrite fields present in the imported Excel
            merged = {k: v for k, v in existing.items() if v is not None}
            merged.update(import_fields)
            # Merge extra_fields: keep existing + add new
            existing_extra = existing.get("extra_fields") or {}
            new_extra = payload.get("extra_fields") or {}
            if existing_extra or new_extra:
                merged["extra_fields"] = {**existing_extra, **new_extra}
            record = build_admin_record(brand, merged, existing_metadata={
                "source_workbook": existing["source_workbook"],
                "source_sheet": existing["source_sheet"],
                "source_row_number": existing["source_row_number"],
            })
            repository.update_product(brand, existing["id"], record)
            updated += 1
        else:
            record = build_admin_record(brand, payload)
            repository.create_product(brand, record)
            created += 1

    wb.close()
    clear_fine_table_cache()
    return {"created": created, "updated": updated, "skus": imported_skus, "message": f"导入完成：新增 {created} 条，更新 {updated} 条"}
