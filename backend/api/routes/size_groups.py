from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from api.operation_log_utils import build_changed_fields, summarize_changes, write_operation_log
from storage.size_group_repository import SizeGroupInUseError, SizeGroupRepository


router = APIRouter(prefix="/size-groups", tags=["size-groups"])


class SizeGroupItemWriteRequest(BaseModel):
    size_name: str = Field(min_length=1, max_length=100)
    barcode: str = Field(min_length=1, max_length=100)

    @field_validator("size_name", "barcode")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


class SizeGroupWriteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    items: list[SizeGroupItemWriteRequest] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("尺码组名称不能为空")
        return normalized

    @model_validator(mode="after")
    def validate_unique_items(self):
        size_names = [item.size_name for item in self.items]
        barcodes = [item.barcode for item in self.items]
        if len(size_names) != len(set(size_names)):
            raise ValueError("尺码不能重复")
        if len(barcodes) != len(set(barcodes)):
            raise ValueError("条码不能重复")
        return self


def _repository(request: Request) -> SizeGroupRepository:
    return SizeGroupRepository(request.app.state.inventory_repository.engine)


def _group_log_payload(group: dict[str, object]) -> dict[str, object]:
    return {
        "name": group.get("name"),
        "items": group.get("items", []),
        "product_count": group.get("product_count", 0),
    }


SIZE_GROUP_LOG_FIELD_LABELS = {
    "name": "尺码组名称",
    "items": "尺码明细",
    "product_count": "使用商品数",
}


@router.get("")
def list_size_groups(request: Request):
    return {"items": _repository(request).list_groups()}


@router.post("")
def create_size_group(request: Request, payload: SizeGroupWriteRequest):
    try:
        item = _repository(request).create_group(
            name=payload.name,
            items=[entry.model_dump() for entry in payload.items],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_operation_log(
        request,
        module="size_group",
        action="create",
        entity_type="size_group",
        entity_id=item["id"],
        entity_label=str(item["name"]),
        summary=f"新增尺码组 {item['name']}",
        after_data=_group_log_payload(item),
    )
    return {"item": item, "message": "创建成功"}


@router.put("/{size_group_id}")
def update_size_group(request: Request, size_group_id: int, payload: SizeGroupWriteRequest):
    existing = _repository(request).get_group(size_group_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="尺码组不存在")
    try:
        item = _repository(request).update_group(
            size_group_id,
            name=payload.name,
            items=[entry.model_dump() for entry in payload.items],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="尺码组不存在")
    before_data = _group_log_payload(existing)
    after_data = _group_log_payload(item)
    changes = build_changed_fields(before_data, after_data, SIZE_GROUP_LOG_FIELD_LABELS)
    write_operation_log(
        request,
        module="size_group",
        action="update",
        entity_type="size_group",
        entity_id=size_group_id,
        entity_label=str(item["name"]),
        summary=summarize_changes("编辑尺码组", str(item["name"]), changes),
        changed_fields=changes,
        before_data=before_data,
        after_data=after_data,
    )
    return {"item": item, "message": "更新成功"}


@router.delete("/{size_group_id}")
def delete_size_group(request: Request, size_group_id: int):
    existing = _repository(request).get_group(size_group_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="尺码组不存在")
    try:
        deleted = _repository(request).delete_group(size_group_id)
    except SizeGroupInUseError as exc:
        raise HTTPException(status_code=409, detail=f"该尺码组已被 {exc.product_count} 个商品使用，无法删除") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="尺码组不存在")
    write_operation_log(
        request,
        module="size_group",
        action="delete",
        entity_type="size_group",
        entity_id=size_group_id,
        entity_label=str(existing["name"]),
        summary=f"删除尺码组 {existing['name']}",
        before_data=_group_log_payload(existing),
    )
    return {"message": "删除成功"}
