from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request

from storage.operation_log_repository import clean_payload


PRODUCT_FIELD_LABELS = {
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

INVENTORY_FIELD_LABELS = {
    "document_number": "单据编号",
    "date": "日期",
    "supplier": "供应商/单位",
    "total_count": "总数",
    "amount": "金额",
    "warehouse": "仓库",
    "document_type": "单据类型",
    "handler": "经手人",
    "summary": "摘要",
    "additional_note": "附加说明",
}

DETAIL_FIELD_LABELS = {
    "product_code": "商品编号",
    "product_name": "商品全名",
    "color_spec": "颜色及规格",
    "color_barcode": "颜色条码",
    "color_name": "颜色名称",
    "size_quantities": "尺码数量",
    "quantity": "数量",
    "unit_price": "单价",
    "amount": "金额",
    "remark": "备注",
    "extra_fields": "扩展信息",
}

IGNORED_FIELDS = {
    "created_at",
    "updated_at",
    "date_value",
    "raw_payload",
    "source_workbook",
    "source_sheet",
    "source_row_number",
}

PURCHASE_ORDER_DOCUMENT_TYPE = "进货订单"


def actor_from_request(request: Request) -> Mapping[str, object] | None:
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, Mapping) else None


def inventory_module_for_record(record: Mapping[str, object] | None) -> str:
    if record and str(record.get("document_type") or "").strip() == PURCHASE_ORDER_DOCUMENT_TYPE:
        return "purchase"
    return "inventory"


def product_entity_label(item: Mapping[str, object] | None) -> str:
    if not item:
        return ""
    return str(item.get("sku") or item.get("original_sku") or item.get("id") or "").strip()


def inventory_entity_label(item: Mapping[str, object] | None) -> str:
    if not item:
        return ""
    return str(item.get("document_number") or item.get("summary") or item.get("id") or "").strip()


def detail_entity_label(item: Mapping[str, object] | None) -> str:
    if not item:
        return ""
    return str(item.get("product_code") or item.get("product_name") or item.get("id") or "").strip()


def _normalize_for_compare(value: object) -> object:
    cleaned = clean_payload(value)
    if cleaned is None:
        return ""
    return cleaned


def build_changed_fields(
    before: Mapping[str, object] | None,
    after: Mapping[str, object] | None,
    labels: Mapping[str, str],
) -> list[dict[str, object]]:
    before = before or {}
    after = after or {}
    keys = sorted((set(before.keys()) | set(after.keys())) - IGNORED_FIELDS)
    changes: list[dict[str, object]] = []
    for key in keys:
        before_value = _normalize_for_compare(before.get(key))
        after_value = _normalize_for_compare(after.get(key))
        if before_value == after_value:
            continue
        changes.append({
            "field": key,
            "label": labels.get(key, key),
            "before": before_value,
            "after": after_value,
        })
    return changes


def summarize_changes(prefix: str, label: str, changes: list[dict[str, object]]) -> str:
    target = f" {label}" if label else ""
    if not changes:
        return f"{prefix}{target}"
    field_text = "、".join(str(item.get("label") or item.get("field")) for item in changes[:8])
    suffix = "等字段" if len(changes) > 8 else ""
    return f"{prefix}{target}：修改了 {field_text}{suffix}"


def write_operation_log(
    request: Request,
    *,
    module: str,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    entity_label: str | None = None,
    summary: str,
    changed_fields: object | None = None,
    before_data: object | None = None,
    after_data: object | None = None,
) -> None:
    repository = getattr(request.app.state, "operation_log_repository", None)
    if repository is None:
        return
    repository.create_log(
        module=module,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        summary=summary,
        changed_fields=changed_fields,
        before_data=before_data,
        after_data=after_data,
        user=actor_from_request(request),
    )
