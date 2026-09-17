from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes.images import image_storage_path_for, image_url_for
from api.operation_log_utils import (
    PRODUCT_FIELD_LABELS,
    build_changed_fields,
    product_entity_label,
    summarize_changes,
    write_operation_log,
)
from api.fine_table_cache import clear_fine_table_cache
from api.product_cost_access import redact_product_cost_item, request_can_view_product_cost
from api.product_goods_cache import clear_product_goods_cache
from api.schemas import BatchDeleteRequest, ProductArchiveBrandKey, ProductWriteRequest

from sqlalchemy import distinct as sa_distinct, select as sa_select

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.ni_gendered_costs import FEMALE_KEY, MALE_KEY, GENDER_COSTS_FIELD, normalize_gender_costs
from domain.excluded_skus import is_excluded_sku
from domain.product_auxiliary_attribute_schema import PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS, PRODUCT_AUXILIARY_ATTRIBUTE_TABLE
from domain.schema import PRODUCT_ARCHIVE_TABLES
from domain.size_group_schema import SIZE_GROUPS_TABLE

PRODUCT_COLOR_BARCODE_BRANDS = {
    "cbanner_mens": "cbanner_mens",
    "cbanner_womens": "cbanner_womens",
    "yandou": "cbanner_mens",
    "eblan": "cbanner_mens",
    "smiley": "smiley",
    "ni": "ni",
}
from transform.rows import build_admin_record, filter_extra_fields


router = APIRouter()


def _with_brand_and_image(
    item: dict,
    brand: str,
    settings,
    us3_storage=None,
    *,
    include_cost: bool = True,
) -> dict:
    costs = normalize_gender_costs((item.get("extra_fields") or {}).get(GENDER_COSTS_FIELD)) if include_cost else {}
    result = {
        **item,
        "brand": brand,
        "image_url": image_url_for(brand, item.get("image_path"), settings),
        "image_storage_path": image_storage_path_for(
            brand,
            item.get("image_path"),
            settings,
            us3_storage,
        ),
        "gender_costs": (
            {
                "female": str(costs[FEMALE_KEY]),
                "male": str(costs[MALE_KEY]),
            }
            if FEMALE_KEY in costs and MALE_KEY in costs
            else None
        ),
    }
    return result if include_cost else redact_product_cost_item(result)


def _validate_size_group(request: Request, size_range: object) -> None:
    normalized_size_group = str(size_range or "").strip()
    if not normalized_size_group:
        return
    repository = request.app.state.repository
    with repository.engine.connect() as connection:
        exists = connection.execute(
            sa_select(SIZE_GROUPS_TABLE.c.id)
            .where(SIZE_GROUPS_TABLE.c.name == normalized_size_group)
            .limit(1)
        ).scalar()
    if exists is None:
        raise HTTPException(status_code=400, detail=f"尺码组 {normalized_size_group} 不存在或已被删除")


@router.get("/products/brands")
def list_product_archive_brands(request: Request):
    return {"items": request.app.state.inventory_repository.list_product_archive_brands()}


@router.get("/products")
def list_products(
    request: Request,
    brand: str = Query(...),
    query: str | None = None,
    sku_prefix: str | None = None,
    year: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    settings = request.app.state.settings
    repository = request.app.state.repository
    us3_storage = getattr(request.app.state, "us3_image_storage", None)
    include_cost = request_can_view_product_cost(request)

    if brand == "all":
        payload = repository.list_all_products(query=query, sku_prefix=sku_prefix, page=page, page_size=page_size)
        return {
            **payload,
            "items": [
                _with_brand_and_image(item, item["brand"], settings, us3_storage, include_cost=include_cost)
                for item in payload["items"]
            ],
        }

    if not repository.is_product_archive_brand(brand):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")

    payload = repository.list_products(brand, query=query, sku_prefix=sku_prefix, year=year, page=page, page_size=page_size)
    return {
        **payload,
        "items": [
            _with_brand_and_image(item, brand, settings, us3_storage, include_cost=include_cost)
            for item in payload["items"]
        ],
    }


@router.get("/products/{brand}/years")
def get_product_years(request: Request, brand: str):
    repository = request.app.state.repository
    if brand == "all" or not repository.is_product_archive_brand(brand):
        return {"years": []}
    table = repository._table_for_brand(brand)
    with repository.engine.connect() as connection:
        result = connection.execute(
            sa_select(sa_distinct(table.c.year))
            .where(table.c.year.isnot(None))
            .where(table.c.year != "")
            .order_by(table.c.year)
        )
        raw = [row[0] for row in result if row[0]]

    # Extract year number prefix: "21年春季款" -> "21", "2025" -> "2025"
    import re
    seen: set[str] = set()
    years: list[str] = []
    for val in raw:
        m = re.match(r"(\d+)", str(val))
        if m:
            y = m.group(1)
            # Normalize 2-digit to 4-digit
            if len(y) == 2:
                y = "20" + y
            if y not in seen:
                seen.add(y)
                years.append(y)
    years.sort()
    return {"years": years}


@router.get("/products/color-barcodes")
def list_product_color_barcodes(request: Request, brand: ProductArchiveBrandKey):
    source_brand = PRODUCT_COLOR_BARCODE_BRANDS.get(brand)
    if source_brand is None:
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")

    repository = request.app.state.inventory_repository
    with repository.engine.connect() as connection:
        rows = connection.execute(
            sa_select(
                COLOR_BARCODE_TABLE.c.brand,
                COLOR_BARCODE_TABLE.c.color_barcode,
                COLOR_BARCODE_TABLE.c.color_name,
            )
            .where(COLOR_BARCODE_TABLE.c.brand == source_brand)
            .order_by(COLOR_BARCODE_TABLE.c.color_barcode, COLOR_BARCODE_TABLE.c.color_name)
        ).mappings()
        items = [
            {
                "brand": row["brand"],
                "color_code": row["color_barcode"],
                "color_name": row["color_name"],
            }
            for row in rows
        ]

    return {"items": items, "source_brand": source_brand}


@router.get("/products/auxiliary-options")
def list_product_auxiliary_options(request: Request, brand: ProductArchiveBrandKey):
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    brand_scope = "cbanner_womens" if brand == "cbanner_womens" else "other"
    with repository.engine.connect() as connection:
        rows = connection.execute(
            sa_select(
                PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.attribute_type,
                PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.attribute_name,
            )
            .where(PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.brand_scope == brand_scope)
            .order_by(
                PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.attribute_type,
                PRODUCT_AUXILIARY_ATTRIBUTE_TABLE.c.attribute_name,
            )
        ).mappings()
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        field = PRODUCT_AUXILIARY_ATTRIBUTE_FIELDS.get(str(row["attribute_type"]))
        if field is None:
            continue
        group = grouped.setdefault(
            field,
            {"field": field, "type_name": row["attribute_type"], "options": []},
        )
        group["options"].append(row["attribute_name"])
    return {"brand": brand, "brand_scope": brand_scope, "items": list(grouped.values())}


@router.get("/products/recycle-bin")
def list_product_recycle_bin(
    request: Request,
    brand: ProductArchiveBrandKey | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    settings = request.app.state.settings
    repository = request.app.state.repository
    us3_storage = getattr(request.app.state, "us3_image_storage", None)
    include_cost = request_can_view_product_cost(request)
    if brand is not None and not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    payload = repository.list_recycled_products(
        brand=brand,
        page=page,
        page_size=page_size,
    )
    return {
        **payload,
        "items": [
            _with_brand_and_image(item, item["brand"], settings, us3_storage, include_cost=include_cost)
            for item in payload["items"]
        ],
    }


@router.post("/products/recycle-bin/{brand}/{product_id}/restore")
def restore_product_from_recycle_bin(request: Request, brand: ProductArchiveBrandKey, product_id: int):
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    item = repository.restore_product(brand, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found in recycle bin")
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(item)
    write_operation_log(
        request,
        module="product",
        action="restore",
        entity_type="product",
        entity_id=label,
        entity_label=label,
        summary=f"从回收站恢复商品 {label}",
        after_data={**item, "brand": brand},
    )
    return {"item": {**item, "brand": brand}, "message": "已恢复商品"}


@router.delete("/products/recycle-bin/{brand}/{product_id}")
def permanently_delete_product(request: Request, brand: ProductArchiveBrandKey, product_id: int):
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    item = repository.permanently_delete_product(brand, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found in recycle bin")
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(item)
    write_operation_log(
        request,
        module="product",
        action="permanent_delete",
        entity_type="product",
        entity_id=label,
        entity_label=label,
        summary=f"彻底删除商品 {label}",
        before_data={**item, "brand": brand},
    )
    return {"message": "已彻底删除商品"}


@router.get("/products/{brand}/{product_id}")
def get_product(request: Request, brand: ProductArchiveBrandKey, product_id: int):
    settings = request.app.state.settings
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    item = repository.get_product(brand, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _with_brand_and_image(
        item,
        brand,
        settings,
        getattr(request.app.state, "us3_image_storage", None),
        include_cost=request_can_view_product_cost(request),
    )


@router.post("/products")
def create_product(request: Request, body: ProductWriteRequest):
    if not request.app.state.repository.is_product_archive_brand(body.brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {body.brand}")
    record = build_admin_record(body.brand, body.payload.model_dump(exclude_none=False))
    _validate_size_group(request, record.get("size_range"))
    if is_excluded_sku(record.get("sku"), record.get("original_sku")):
        raise HTTPException(status_code=400, detail="该货号已在永久排除清单中")
    item = request.app.state.repository.create_product(
        body.brand,
        record,
        manual_cost_override=True,
    )
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(item)
    write_operation_log(
        request,
        module="product",
        action="create",
        entity_type="product",
        entity_id=label,
        entity_label=label,
        summary=f"新增商品 {label}",
        after_data={**item, "brand": body.brand},
    )
    return {"item": {**item, "brand": body.brand}, "message": "Product created"}


@router.put("/products/{brand}/{product_id}")
def update_product(request: Request, brand: ProductArchiveBrandKey, product_id: int, body: ProductWriteRequest):
    if body.brand != brand:
        raise HTTPException(status_code=400, detail="Brand mismatch")

    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    existing = repository.get_product(brand, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")

    record = build_admin_record(
        brand,
        body.payload.model_dump(exclude_none=False),
        existing_metadata={
            "source_workbook": existing["source_workbook"],
            "source_sheet": existing["source_sheet"],
            "source_row_number": existing["source_row_number"],
        },
    )
    _validate_size_group(request, record.get("size_range"))
    record["extra_fields"] = filter_extra_fields(existing.get("extra_fields"))
    if is_excluded_sku(record.get("sku"), record.get("original_sku")):
        raise HTTPException(status_code=400, detail="该货号已在永久排除清单中")
    inventory_repository = request.app.state.inventory_repository
    with repository.engine.begin() as connection:
        item = repository.update_product(
            brand,
            product_id,
            record,
            connection=connection,
            manual_cost_override=True,
        )
        replacements = (
            repository.purchase_order_product_code_replacements(
                brand,
                product_id,
                existing,
                item,
                connection=connection,
            )
            if item is not None
            else {}
        )
        purchase_order_sync = inventory_repository.sync_purchase_order_product_codes(
            connection,
            brand=brand,
            replacements=replacements,
            supplier_names=(
                existing.get("supplier_name"),
                item.get("supplier_name") if item is not None else None,
            ),
        )
    if item is None:
        # Re-check after the pre-read in case the row was deleted concurrently.
        raise HTTPException(status_code=404, detail="Product not found")
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(item)
    field_labels = PRODUCT_FIELD_LABELS
    if brand == "cbanner_womens":
        field_labels = {
            **PRODUCT_FIELD_LABELS,
            "upper_height": "鞋帮高度",
        }
    changes = build_changed_fields(existing, item, field_labels)
    sync_summary = ""
    if purchase_order_sync["details"]:
        sync_summary = (
            f"；同步更新 {purchase_order_sync['details']} 条历史采购单明细"
            f"（{purchase_order_sync['documents']} 张采购单）"
        )
    write_operation_log(
        request,
        module="product",
        action="update",
        entity_type="product",
        entity_id=label,
        entity_label=label,
        summary=f"{summarize_changes('编辑商品', label, changes)}{sync_summary}",
        changed_fields=changes,
        before_data={**existing, "brand": brand},
        after_data={**item, "brand": brand},
    )
    return {
        "item": {**item, "brand": brand},
        "purchase_order_sync": purchase_order_sync,
        "message": (
            f"商品已更新，并同步 {purchase_order_sync['details']} 条历史采购单明细"
            if purchase_order_sync["details"]
            else "Product updated"
        ),
    }


@router.delete("/products/{brand}/{product_id}")
def delete_product(request: Request, brand: ProductArchiveBrandKey, product_id: int):
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
    existing = repository.get_product(brand, product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Product not found")
    deleted = request.app.state.repository.delete_product(brand, product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(existing)
    write_operation_log(
        request,
        module="product",
        action="delete",
        entity_type="product",
        entity_id=label,
        entity_label=label,
        summary=f"移入回收站 商品 {label}",
        before_data={**existing, "brand": brand},
    )
    return {"message": "已移入回收站"}


@router.post("/products/batch-delete")
def batch_delete_products(request: Request, body: BatchDeleteRequest):
    repository = request.app.state.repository

    if body.items:
        grouped_ids: dict[str, set[int]] = {}
        for target in body.items:
            grouped_ids.setdefault(target.brand, set()).add(target.id)

        existing_items: list[dict[str, object]] = []
        labels: list[str] = []
        for brand, target_ids in grouped_ids.items():
            if not repository.is_product_archive_brand(brand):
                raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")
            brand_items = repository.get_products_by_ids(brand, sorted(target_ids))
            existing_items.extend({**item, "brand": brand} for item in brand_items)
            labels.extend(product_entity_label(item) for item in brand_items)

        deleted = 0
        with repository.engine.begin() as connection:
            for brand, target_ids in grouped_ids.items():
                deleted += repository.delete_products(
                    brand,
                    sorted(target_ids),
                    connection=connection,
                )

        clear_fine_table_cache()
        clear_product_goods_cache()
        write_operation_log(
            request,
            module="product",
            action="batch_delete",
            entity_type="product",
            entity_id=",".join(labels),
            entity_label=f"{deleted} 条商品",
            summary=f"批量移入回收站 商品 {deleted} 条",
            before_data={
                "brands": {brand: len(ids) for brand, ids in grouped_ids.items()},
                "item_count": deleted,
                "items": existing_items[:200],
                "labels": labels[:200],
            },
        )
        return {"deleted": deleted, "message": f"已移入回收站 {deleted} 条商品"}

    if not body.brand or not body.ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    if not repository.is_product_archive_brand(body.brand):
        raise HTTPException(status_code=400, detail=f"Invalid brand: {body.brand}")
    existing_items = repository.get_products_by_ids(body.brand, body.ids)
    deleted = repository.delete_products(body.brand, body.ids)
    clear_fine_table_cache()
    clear_product_goods_cache()
    labels = [product_entity_label(item) for item in existing_items]
    write_operation_log(
        request,
        module="product",
        action="batch_delete",
        entity_type="product",
        entity_id=",".join(labels),
        entity_label=f"{deleted} 条商品",
        summary=f"批量移入回收站 商品 {deleted} 条",
        before_data={
            "brand": body.brand,
            "item_count": deleted,
            "items": existing_items[:200],
            "labels": labels[:200],
        },
    )
    return {"deleted": deleted, "message": f"已移入回收站 {deleted} 条商品"}
