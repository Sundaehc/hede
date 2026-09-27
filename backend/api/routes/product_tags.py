from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, select

from api.operation_log_utils import build_changed_fields, summarize_changes, write_operation_log
from domain.product_tag_schema import (
    PRODUCT_TAG_ASSIGNMENTS_TABLE,
    PRODUCT_TAG_DEFINITIONS_TABLE,
)
from domain.product_tag_generation import rebuild_product_tags


router = APIRouter(prefix="/product-tags", tags=["product-tags"])

TAG_GROUPS = ("品类", "季节", "年份", "等级", "材质", "结构", "风格", "功能", "运营", "数据质量")


class ProductTagUpdateRequest(BaseModel):
    tag_name: str = Field(min_length=1, max_length=100)
    tag_group: str = Field(min_length=1, max_length=50)
    sort_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True

    @field_validator("tag_name", "tag_group")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


TAG_LOG_FIELD_LABELS = {
    "tag_name": "标签名称",
    "tag_group": "标签分组",
    "sort_order": "排序",
    "is_active": "启用状态",
}


def _serialize_tag(row: dict[str, object]) -> dict[str, object]:
    return dict(row)


def _validate_brand(request: Request, brand: str) -> None:
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")


@router.get("/metadata")
def get_tag_metadata():
    return {
        "groups": list(TAG_GROUPS),
        "sources": ["rule"],
        "statuses": ["confirmed"],
    }


@router.post("/rebuild-from-products")
def rebuild_tags_from_products(request: Request):
    result = rebuild_product_tags(request.app.state.repository)
    write_operation_log(
        request,
        module="product_tag",
        action="rebuild",
        entity_type="product_tag_catalog",
        summary="根据商品信息档案重建商品标签",
        after_data=result,
    )
    return {"result": result, "message": "已清空旧标签并根据商品信息档案重建"}


@router.get("")
def list_tag_definitions(
    request: Request,
    group: str | None = None,
    query: str | None = None,
    include_inactive: bool = False,
):
    table = PRODUCT_TAG_DEFINITIONS_TABLE
    conditions = []
    if not include_inactive:
        conditions.append(table.c.is_active.is_(True))
    if group and group != "all":
        conditions.append(table.c.tag_group == group.strip())
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        conditions.append((table.c.tag_name.ilike(pattern)) | (table.c.tag_code.ilike(pattern)))
    statement = select(table).order_by(table.c.tag_group, table.c.sort_order, table.c.id)
    if conditions:
        statement = statement.where(and_(*conditions))
    with request.app.state.repository.engine.connect() as connection:
        items = [dict(row) for row in connection.execute(statement).mappings()]
    return {"items": [_serialize_tag(item) for item in items], "total": len(items)}


@router.put("/definitions/{tag_id}")
def update_tag_definition(request: Request, tag_id: int, payload: ProductTagUpdateRequest):
    if payload.tag_group not in TAG_GROUPS:
        raise HTTPException(status_code=400, detail="无效的标签分组")
    table = PRODUCT_TAG_DEFINITIONS_TABLE
    with request.app.state.repository.engine.begin() as connection:
        existing = connection.execute(select(table).where(table.c.id == tag_id)).mappings().first()
        if existing is None:
            raise HTTPException(status_code=404, detail="标签不存在")
        row = connection.execute(
            table.update()
            .where(table.c.id == tag_id)
            .values(
                tag_name=payload.tag_name,
                tag_group=payload.tag_group,
                sort_order=payload.sort_order,
                is_active=payload.is_active,
                is_manual_override=True,
            )
            .returning(table)
        ).mappings().one()
    item = dict(row)
    before_data = {field: existing[field] for field in TAG_LOG_FIELD_LABELS}
    after_data = {field: item[field] for field in TAG_LOG_FIELD_LABELS}
    changes = build_changed_fields(before_data, after_data, TAG_LOG_FIELD_LABELS)
    write_operation_log(
        request,
        module="product_tag",
        action="update",
        entity_type="tag",
        entity_id=tag_id,
        entity_label=str(item["tag_name"]),
        summary=summarize_changes("编辑商品标签", str(item["tag_name"]), changes),
        changed_fields=changes,
        before_data=before_data,
        after_data=after_data,
    )
    return {"item": item, "message": "标签已更新，人工修改将在重建时保留"}


@router.get("/assignments")
def list_product_tag_assignments(
    request: Request,
    brand: str = Query(..., min_length=1),
    product_id: int = Query(..., gt=0),
    status: str = "confirmed",
):
    _validate_brand(request, brand)
    assignments = PRODUCT_TAG_ASSIGNMENTS_TABLE
    tags = PRODUCT_TAG_DEFINITIONS_TABLE
    conditions = [assignments.c.brand == brand, assignments.c.product_id == product_id]
    if status != "all":
        conditions.append(assignments.c.status == status)
    statement = select(assignments, tags.c.tag_code, tags.c.tag_name, tags.c.tag_group).join(tags, tags.c.id == assignments.c.tag_id).where(and_(*conditions)).order_by(tags.c.tag_group, tags.c.sort_order, tags.c.id)
    with request.app.state.repository.engine.connect() as connection:
        items = [dict(row) for row in connection.execute(statement).mappings()]
    return {"items": items, "total": len(items)}
