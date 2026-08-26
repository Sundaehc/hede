from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from api.fine_table_cache import clear_fine_table_cache
from api.operation_log_utils import build_changed_fields, summarize_changes, write_operation_log
from api.product_goods_cache import clear_product_goods_cache
from domain.color_barcode_schema import COLOR_BARCODE_TABLE


router = APIRouter(prefix="/color-barcodes", tags=["color-barcodes"])

COLOR_BRAND_LABELS = {
    "cbanner_mens": "千百度男鞋",
    "cbanner_womens": "千百度女鞋",
    "smiley": "笑脸",
    "ni": "NI",
}
COLOR_FIELD_LABELS = {
    "brand": "品牌",
    "color_barcode": "颜色代码",
    "color_name": "颜色名称",
}


class ColorBarcodeWriteRequest(BaseModel):
    brand: str = Field(min_length=1, max_length=100)
    color_barcode: str = Field(min_length=1, max_length=100)
    color_name: str = Field(min_length=1, max_length=200)

    @field_validator("brand", "color_barcode", "color_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


def _engine(request: Request):
    return request.app.state.inventory_repository.engine


def _brand_label(brand: object) -> str:
    normalized = str(brand or "").strip()
    return COLOR_BRAND_LABELS.get(normalized, normalized)


def _serialize_item(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "brand_label": _brand_label(row.get("brand")),
    }


def _clear_color_cache(request: Request) -> None:
    repository = getattr(request.app.state, "repository", None)
    clear_cache = getattr(repository, "clear_color_code_cache", None)
    if callable(clear_cache):
        clear_cache()
    clear_fine_table_cache()
    clear_product_goods_cache()


def _sync_products(
    request: Request,
    connection,
    *,
    source_brand: str,
    color_name: str | None,
    color_code: str | None,
    previous_color_name: str | None = None,
    previous_color_code: str | None = None,
    remove: bool = False,
    sync_color_name: bool = False,
) -> dict[str, object]:
    repository = request.app.state.repository
    return repository.sync_color_mapping_to_products(
        source_brand=source_brand,
        color_name=color_name,
        color_code=color_code,
        previous_color_name=previous_color_name,
        previous_color_code=previous_color_code,
        remove=remove,
        sync_color_name=sync_color_name,
        connection=connection,
    )


def _duplicate_message(connection, payload: ColorBarcodeWriteRequest, *, exclude_id: int | None = None) -> str | None:
    table = COLOR_BARCODE_TABLE
    code_statement = select(table.c.id).where(
        table.c.brand == payload.brand,
        table.c.color_barcode == payload.color_barcode,
    )
    name_statement = select(table.c.id).where(
        table.c.brand == payload.brand,
        table.c.color_name == payload.color_name,
    )
    if exclude_id is not None:
        code_statement = code_statement.where(table.c.id != exclude_id)
        name_statement = name_statement.where(table.c.id != exclude_id)
    if connection.execute(code_statement.limit(1)).scalar() is not None:
        return f"{_brand_label(payload.brand)}中颜色代码 {payload.color_barcode} 已存在"
    if connection.execute(name_statement.limit(1)).scalar() is not None:
        return f"{_brand_label(payload.brand)}中颜色名称 {payload.color_name} 已存在"
    return None


@router.get("/brands")
def list_color_barcode_brands(request: Request):
    table = COLOR_BARCODE_TABLE
    statement = (
        select(table.c.brand, func.count().label("total"))
        .group_by(table.c.brand)
        .order_by(table.c.brand)
    )
    with _engine(request).connect() as connection:
        rows = connection.execute(statement).mappings().all()
    counts = {str(row["brand"]): int(row["total"] or 0) for row in rows}
    brands = list(dict.fromkeys([*COLOR_BRAND_LABELS, *counts]))
    items = [
        {
            "brand": brand,
            "brand_label": _brand_label(brand),
            "total": counts.get(brand, 0),
        }
        for brand in brands
    ]
    items.sort(key=lambda item: (list(COLOR_BRAND_LABELS).index(item["brand"]) if item["brand"] in COLOR_BRAND_LABELS else 999, item["brand_label"]))
    return {"items": items}


@router.get("")
def list_color_barcodes(
    request: Request,
    brand: str = Query(..., min_length=1),
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    table = COLOR_BARCODE_TABLE
    conditions = [table.c.brand == brand.strip()]
    normalized_query = str(query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        conditions.append(or_(table.c.color_barcode.ilike(pattern), table.c.color_name.ilike(pattern)))
    criterion = and_(*conditions)
    count_statement = select(func.count()).select_from(table).where(criterion)
    items_statement = (
        select(table)
        .where(criterion)
        .order_by(table.c.color_barcode, table.c.color_name, table.c.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    with _engine(request).connect() as connection:
        total = int(connection.execute(count_statement).scalar_one())
        rows = [dict(row) for row in connection.execute(items_statement).mappings()]
    return {
        "items": [_serialize_item(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
def create_color_barcode(request: Request, payload: ColorBarcodeWriteRequest):
    table = COLOR_BARCODE_TABLE
    values = {
        "brand": payload.brand,
        "color_barcode": payload.color_barcode,
        "color_name": payload.color_name,
        "source_workbook": "manual_admin",
        "source_sheet": payload.brand,
        "source_row_number": "manual",
        "raw_payload": {
            "品牌": payload.brand,
            "颜色代码": payload.color_barcode,
            "颜色名称": payload.color_name,
        },
    }
    try:
        with _engine(request).begin() as connection:
            duplicate = _duplicate_message(connection, payload)
            if duplicate:
                raise HTTPException(status_code=400, detail=duplicate)
            row = connection.execute(insert(table).values(**values).returning(table)).mappings().one()
            sync_result = _sync_products(
                request,
                connection,
                source_brand=payload.brand,
                color_name=payload.color_name,
                color_code=payload.color_barcode,
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="同一品牌下颜色代码不能重复") from exc
    item = _serialize_item(dict(row))
    _clear_color_cache(request)
    write_operation_log(
        request,
        module="color_barcode",
        action="create",
        entity_type="color_barcode",
        entity_id=item["id"],
        entity_label=f"{item['brand_label']} / {item['color_name']} / {item['color_barcode']}",
        summary=f"新增颜色 {item['brand_label']} / {item['color_name']} / {item['color_barcode']}；同步商品档案 {sync_result['updated']} 条",
        after_data={**item, "synced_products": sync_result},
    )
    return {"item": item, "message": f"新增成功，已同步 {sync_result['updated']} 条商品档案", "synced": sync_result}


@router.put("/{color_id}")
def update_color_barcode(request: Request, color_id: int, payload: ColorBarcodeWriteRequest):
    table = COLOR_BARCODE_TABLE
    try:
        with _engine(request).begin() as connection:
            existing_row = connection.execute(select(table).where(table.c.id == color_id)).mappings().first()
            if existing_row is None:
                raise HTTPException(status_code=404, detail="颜色记录不存在")
            duplicate = _duplicate_message(connection, payload, exclude_id=color_id)
            if duplicate:
                raise HTTPException(status_code=400, detail=duplicate)
            values = {
                "brand": payload.brand,
                "color_barcode": payload.color_barcode,
                "color_name": payload.color_name,
                "source_workbook": "manual_admin",
                "source_sheet": payload.brand,
                "source_row_number": "manual",
                "raw_payload": {
                    "品牌": payload.brand,
                    "颜色代码": payload.color_barcode,
                    "颜色名称": payload.color_name,
                },
                "updated_at": func.date_trunc("minute", func.now()),
            }
            row = connection.execute(
                update(table).where(table.c.id == color_id).values(**values).returning(table)
            ).mappings().one()
            old_brand = str(existing_row.get("brand") or "").strip()
            if old_brand == payload.brand:
                sync_result = _sync_products(
                    request,
                    connection,
                    source_brand=payload.brand,
                    color_name=payload.color_name,
                    color_code=payload.color_barcode,
                    previous_color_name=str(existing_row.get("color_name") or "").strip(),
                    previous_color_code=str(existing_row.get("color_barcode") or "").strip(),
                    sync_color_name=(
                        str(existing_row.get("color_name") or "").strip() != payload.color_name
                    ),
                )
            else:
                removed_result = _sync_products(
                    request,
                    connection,
                    source_brand=old_brand,
                    color_name=None,
                    color_code=None,
                    previous_color_name=str(existing_row.get("color_name") or "").strip(),
                    previous_color_code=str(existing_row.get("color_barcode") or "").strip(),
                    remove=True,
                )
                applied_result = _sync_products(
                    request,
                    connection,
                    source_brand=payload.brand,
                    color_name=payload.color_name,
                    color_code=payload.color_barcode,
                )
                sync_result = {
                    "updated": int(removed_result["updated"]) + int(applied_result["updated"]),
                    "removed": removed_result,
                    "applied": applied_result,
                }
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="同一品牌下颜色代码不能重复") from exc
    before = _serialize_item(dict(existing_row))
    item = _serialize_item(dict(row))
    _clear_color_cache(request)
    changes = build_changed_fields(before, item, COLOR_FIELD_LABELS)
    label = f"{item['brand_label']} / {item['color_name']} / {item['color_barcode']}"
    write_operation_log(
        request,
        module="color_barcode",
        action="update",
        entity_type="color_barcode",
        entity_id=color_id,
        entity_label=label,
        summary=f"{summarize_changes('编辑颜色', label, changes)}；同步商品档案 {sync_result['updated']} 条",
        changed_fields=changes,
        before_data=before,
        after_data={**item, "synced_products": sync_result},
    )
    return {"item": item, "message": f"保存成功，已同步 {sync_result['updated']} 条商品档案", "synced": sync_result}


@router.delete("/{color_id}")
def delete_color_barcode(request: Request, color_id: int):
    table = COLOR_BARCODE_TABLE
    with _engine(request).begin() as connection:
        row = connection.execute(delete(table).where(table.c.id == color_id).returning(table)).mappings().first()
        if row is not None:
            sync_result = _sync_products(
                request,
                connection,
                source_brand=str(row.get("brand") or "").strip(),
                color_name=None,
                color_code=None,
                previous_color_name=str(row.get("color_name") or "").strip(),
                previous_color_code=str(row.get("color_barcode") or "").strip(),
                remove=True,
            )
    if row is None:
        raise HTTPException(status_code=404, detail="颜色记录不存在")
    item = _serialize_item(dict(row))
    _clear_color_cache(request)
    label = f"{item['brand_label']} / {item['color_name']} / {item['color_barcode']}"
    write_operation_log(
        request,
        module="color_barcode",
        action="delete",
        entity_type="color_barcode",
        entity_id=color_id,
        entity_label=label,
        summary=f"删除颜色 {label}；清空商品档案颜色代码 {sync_result['updated']} 条",
        before_data={**item, "synced_products": sync_result},
    )
    return {"message": f"删除成功，已清空 {sync_result['updated']} 条商品档案颜色代码", "synced": sync_result}
