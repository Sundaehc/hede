from __future__ import annotations

import io
import urllib.parse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from api.excel_export import style_excel_worksheet
from api.operation_log_utils import build_changed_fields, summarize_changes, write_operation_log
from domain.product_auxiliary_attribute_schema import (
    PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS,
    PRODUCT_AUXILIARY_ATTRIBUTE_TABLE,
)


router = APIRouter(
    prefix="/product-auxiliary-attributes",
    tags=["product-auxiliary-attributes"],
)

AUXILIARY_ATTRIBUTE_SCOPE_LABELS = {
    "cbanner_womens": "千百度女鞋",
    "other": "其他品牌",
}
AUXILIARY_ATTRIBUTE_FIELD_LABELS = {
    "brand_scope": "适用品牌",
    "attribute_type": "属性类型",
    "attribute_name": "属性值",
}


class AuxiliaryAttributeWriteRequest(BaseModel):
    brand_scope: str = Field(min_length=1, max_length=100)
    attribute_type: str = Field(min_length=1, max_length=100)
    attribute_name: str = Field(min_length=1, max_length=500)

    @field_validator("brand_scope", "attribute_type", "attribute_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


def _engine(request: Request):
    return request.app.state.inventory_repository.engine


def _scope_label(scope: object) -> str:
    normalized = str(scope or "").strip()
    return AUXILIARY_ATTRIBUTE_SCOPE_LABELS.get(normalized, normalized)


def _validate_payload(payload: AuxiliaryAttributeWriteRequest) -> None:
    if payload.brand_scope not in AUXILIARY_ATTRIBUTE_SCOPE_LABELS:
        raise HTTPException(status_code=400, detail="无效的适用品牌")
    if payload.attribute_type not in PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS:
        raise HTTPException(status_code=400, detail="无效的属性类型")


def _serialize_item(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "brand_scope_label": _scope_label(row.get("brand_scope")),
        "product_field": PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS.get(
            str(row.get("attribute_type") or "")
        ),
    }


def _conditions(brand_scope: str, attribute_type: str | None, query: str | None):
    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    conditions = [
        table.c.brand_scope == brand_scope.strip(),
        table.c.attribute_type.in_(tuple(PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS)),
    ]
    normalized_type = str(attribute_type or "").strip()
    if normalized_type and normalized_type != "all":
        conditions.append(table.c.attribute_type == normalized_type)
    normalized_query = str(query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        conditions.append(
            or_(
                table.c.attribute_type.ilike(pattern),
                table.c.attribute_name.ilike(pattern),
            )
        )
    return and_(*conditions)


def _build_auxiliary_attribute_export_workbook(rows) -> Workbook:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "辅助属性"
    worksheet.append(["属性类型", "属性值"])
    for row in rows:
        worksheet.append([row["attribute_type"] or "", row["attribute_name"] or ""])
    style_excel_worksheet(
        worksheet,
        width_by_header={"属性类型": 20, "属性值": 36},
    )
    return workbook


def _stream_auxiliary_attribute_export(
    workbook: Workbook,
    filename: str,
) -> StreamingResponse:
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}",
            "Content-Length": str(buffer.getbuffer().nbytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/metadata")
def get_auxiliary_attribute_metadata(request: Request):
    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    with _engine(request).connect() as connection:
        scope_rows = connection.execute(
            select(table.c.brand_scope, func.count().label("total"))
            .where(table.c.attribute_type.in_(tuple(PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS)))
            .group_by(table.c.brand_scope)
        ).mappings().all()
    counts = {str(row["brand_scope"]): int(row["total"] or 0) for row in scope_rows}
    return {
        "scopes": [
            {
                "value": value,
                "label": label,
                "total": counts.get(value, 0),
            }
            for value, label in AUXILIARY_ATTRIBUTE_SCOPE_LABELS.items()
        ],
        "attribute_types": [
            {"value": attribute_type, "field": field}
            for attribute_type, field in PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS.items()
        ],
    }


@router.get("")
def list_auxiliary_attributes(
    request: Request,
    brand_scope: str = Query(..., min_length=1),
    attribute_type: str | None = None,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    normalized_scope = brand_scope.strip()
    if normalized_scope not in AUXILIARY_ATTRIBUTE_SCOPE_LABELS:
        raise HTTPException(status_code=400, detail="无效的适用品牌")
    normalized_type = str(attribute_type or "").strip()
    if normalized_type and normalized_type != "all" and normalized_type not in PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS:
        raise HTTPException(status_code=400, detail="无效的属性类型")

    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    criterion = _conditions(normalized_scope, normalized_type, query)
    count_statement = select(func.count()).select_from(table).where(criterion)
    items_statement = (
        select(table)
        .where(criterion)
        .order_by(table.c.attribute_type, table.c.attribute_name, table.c.id)
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


@router.get("/export")
def export_auxiliary_attributes(
    request: Request,
    brand_scope: str = Query(..., min_length=1),
    attribute_type: str | None = None,
    query: str | None = None,
):
    normalized_scope = brand_scope.strip()
    if normalized_scope not in AUXILIARY_ATTRIBUTE_SCOPE_LABELS:
        raise HTTPException(status_code=400, detail="无效的适用品牌")
    normalized_type = str(attribute_type or "").strip()
    if (
        normalized_type
        and normalized_type != "all"
        and normalized_type not in PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS
    ):
        raise HTTPException(status_code=400, detail="无效的属性类型")
    normalized_query = str(query or "").strip()

    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    statement = (
        select(table.c.attribute_type, table.c.attribute_name)
        .where(_conditions(normalized_scope, normalized_type, normalized_query))
        .order_by(table.c.attribute_type, table.c.attribute_name, table.c.id)
    )
    with _engine(request).connect() as connection:
        rows = connection.execute(statement).mappings().all()

    scope_label = _scope_label(normalized_scope)
    type_label = normalized_type if normalized_type and normalized_type != "all" else "全部类型"
    write_operation_log(
        request,
        module="product_auxiliary_attribute",
        action="export",
        entity_type="product_auxiliary_attribute",
        entity_label=scope_label,
        summary=f"导出辅助属性 {scope_label} / {type_label} {len(rows)} 条{f'（关键词：{normalized_query}）' if normalized_query else ''}",
        after_data={
            "count": len(rows),
            "brand_scope": normalized_scope,
            "attribute_type": normalized_type,
            "query": normalized_query,
        },
    )
    workbook = _build_auxiliary_attribute_export_workbook(rows)
    return _stream_auxiliary_attribute_export(
        workbook,
        f"辅助属性管理_{scope_label}_{type_label}.xlsx",
    )


@router.post("")
def create_auxiliary_attribute(request: Request, payload: AuxiliaryAttributeWriteRequest):
    _validate_payload(payload)
    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    values = {
        "brand_scope": payload.brand_scope,
        "attribute_type": payload.attribute_type,
        "attribute_name": payload.attribute_name,
        "source_workbook": "manual_admin",
        "source_sheet": payload.brand_scope,
        "source_row_number": "manual",
    }
    try:
        with _engine(request).begin() as connection:
            row = connection.execute(
                insert(table).values(**values).returning(table)
            ).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="相同适用品牌和属性类型下，该属性值已存在") from exc

    item = _serialize_item(dict(row))
    label = f"{item['brand_scope_label']} / {item['attribute_type']} / {item['attribute_name']}"
    write_operation_log(
        request,
        module="product_auxiliary_attribute",
        action="create",
        entity_type="product_auxiliary_attribute",
        entity_id=item["id"],
        entity_label=label,
        summary=f"新增辅助属性 {label}",
        after_data=item,
    )
    return {"item": item, "message": "新增成功"}


@router.put("/{attribute_id}")
def update_auxiliary_attribute(
    request: Request,
    attribute_id: int,
    payload: AuxiliaryAttributeWriteRequest,
):
    _validate_payload(payload)
    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    values = {
        "brand_scope": payload.brand_scope,
        "attribute_type": payload.attribute_type,
        "attribute_name": payload.attribute_name,
        "source_workbook": "manual_admin",
        "source_sheet": payload.brand_scope,
        "source_row_number": "manual",
        "updated_at": func.date_trunc("minute", func.now()),
    }
    try:
        with _engine(request).begin() as connection:
            existing = connection.execute(
                select(table).where(table.c.id == attribute_id)
            ).mappings().first()
            if existing is None:
                raise HTTPException(status_code=404, detail="辅助属性不存在")
            row = connection.execute(
                update(table)
                .where(table.c.id == attribute_id)
                .values(**values)
                .returning(table)
            ).mappings().one()
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="相同适用品牌和属性类型下，该属性值已存在") from exc

    before = _serialize_item(dict(existing))
    item = _serialize_item(dict(row))
    changes = build_changed_fields(before, item, AUXILIARY_ATTRIBUTE_FIELD_LABELS)
    label = f"{item['brand_scope_label']} / {item['attribute_type']} / {item['attribute_name']}"
    write_operation_log(
        request,
        module="product_auxiliary_attribute",
        action="update",
        entity_type="product_auxiliary_attribute",
        entity_id=attribute_id,
        entity_label=label,
        summary=summarize_changes("编辑辅助属性", label, changes),
        changed_fields=changes,
        before_data=before,
        after_data=item,
    )
    return {"item": item, "message": "保存成功"}


@router.delete("/{attribute_id}")
def delete_auxiliary_attribute(request: Request, attribute_id: int):
    table = PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
    with _engine(request).begin() as connection:
        row = connection.execute(
            delete(table).where(table.c.id == attribute_id).returning(table)
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="辅助属性不存在")

    item = _serialize_item(dict(row))
    label = f"{item['brand_scope_label']} / {item['attribute_type']} / {item['attribute_name']}"
    write_operation_log(
        request,
        module="product_auxiliary_attribute",
        action="delete",
        entity_type="product_auxiliary_attribute",
        entity_id=attribute_id,
        entity_label=label,
        summary=f"删除辅助属性 {label}",
        before_data=item,
    )
    return {"message": "删除成功"}
