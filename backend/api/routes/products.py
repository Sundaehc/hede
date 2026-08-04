from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes.images import image_url_for
from api.operation_log_utils import (
    PRODUCT_FIELD_LABELS,
    build_changed_fields,
    product_entity_label,
    summarize_changes,
    write_operation_log,
)
from api.fine_table_cache import clear_fine_table_cache
from api.product_goods_cache import clear_product_goods_cache
from api.schemas import BatchDeleteRequest, BrandKey, ProductWriteRequest

from sqlalchemy import distinct as sa_distinct, func as sa_func, or_ as sa_or, select as sa_select

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.excluded_skus import is_excluded_sku
from domain.schema import PRODUCT_TABLES
from domain.size_group_schema import SIZE_GROUPS_TABLE
from domain.smiley_schema import SMILEY_FINE_TABLE

ALL_BRAND_KEYS = ["cbanner_mens", "cbanner_womens", "yandou", "eblan"]
SMILEY_PRODUCT_ARCHIVE_BRAND = "smiley"
PRODUCT_COLOR_BARCODE_BRANDS = {
    "cbanner_mens": "cbanner_mens",
    "cbanner_womens": "cbanner_womens",
    "yandou": "cbanner_mens",
    "eblan": "cbanner_mens",
}
from transform.rows import build_admin_record, filter_extra_fields


router = APIRouter()


def _with_brand_and_image(item: dict, brand: str, settings) -> dict:
    return {
        **item,
        "brand": brand,
        "image_url": image_url_for(brand, item.get("image_path"), settings),
    }


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


def _smiley_product_base_item(item: dict, settings) -> dict:
    return {
        "id": item["id"],
        "brand": SMILEY_PRODUCT_ARCHIVE_BRAND,
        "image_path": item.get("image_path"),
        "image_url": image_url_for(SMILEY_PRODUCT_ARCHIVE_BRAND, item.get("image_path"), settings),
        "sku": item.get("sku"),
        "original_sku": item.get("original_sku"),
        "product_name": item.get("product_name"),
        "group_name": None,
        "product_level": None,
        "cost": item.get("cost"),
        "factory_sku": item.get("factory_sku") or item.get("factory_code"),
        "factory_code": item.get("factory_code"),
        "market_price": item.get("market_price"),
        "barcode": item.get("barcode"),
        "accessories": item.get("accessories"),
        "color": None,
        "season_category": item.get("season_category"),
        "year": None,
        "upper_material": item.get("upper_material"),
        "lining_material": item.get("lining_material"),
        "outsole_material": item.get("outsole_material"),
        "insole_material": item.get("insole_material"),
        "execution_standard": item.get("execution_standard"),
        "heel_height": None,
        "shoe_width": None,
        "shoe_length": None,
        "shaft_circumference": None,
        "shaft_height": None,
        "internal_height_increase": None,
        "internal_height_note": None,
        "upper_height": None,
        "toe_shape": None,
        "closure_type": None,
        "shoe_box_spec": item.get("shoe_box_spec"),
        "shoe_box_type": None,
        "selling_points": None,
        "first_order_time": item.get("first_order_date"),
        "size_range": None,
        "product_model": None,
        "supplier_name": None,
        "color_code": None,
        "launch_date": None,
        "source_workbook": item.get("source_workbook") or "",
        "source_sheet": item.get("source_sheet") or "",
        "source_row_number": str(item.get("source_row_number") or ""),
    }


def _list_smiley_product_base_info(
    request: Request,
    *,
    query: str | None,
    page: int,
    page_size: int,
) -> dict:
    settings = request.app.state.settings
    repository = request.app.state.repository
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    normalized_query = (query or "").strip()

    with repository.engine.connect() as connection:
        snapshot_date = connection.execute(
            sa_select(sa_func.max(SMILEY_FINE_TABLE.c.snapshot_date))
        ).scalar()
        if snapshot_date is None:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "snapshot_date": None}

        # Preserve the newest version of every SKU across all imported snapshots.
        latest_rows = sa_select(
            SMILEY_FINE_TABLE.c.id,
            sa_func.row_number()
            .over(
                partition_by=SMILEY_FINE_TABLE.c.sku,
                order_by=(
                    SMILEY_FINE_TABLE.c.snapshot_date.desc(),
                    SMILEY_FINE_TABLE.c.updated_at.desc().nulls_last(),
                    SMILEY_FINE_TABLE.c.id.desc(),
                ),
            )
            .label("row_rank"),
        ).subquery("smiley_latest_rows")
        source = SMILEY_FINE_TABLE.join(
            latest_rows,
            SMILEY_FINE_TABLE.c.id == latest_rows.c.id,
        )
        conditions = [latest_rows.c.row_rank == 1]
        if normalized_query:
            term = f"%{normalized_query}%"
            conditions.append(sa_or(
                SMILEY_FINE_TABLE.c.sku.ilike(term),
                SMILEY_FINE_TABLE.c.original_sku.ilike(term),
                SMILEY_FINE_TABLE.c.factory_code.ilike(term),
                SMILEY_FINE_TABLE.c.factory_sku.ilike(term),
                SMILEY_FINE_TABLE.c.product_name.ilike(term),
                SMILEY_FINE_TABLE.c.barcode.ilike(term),
            ))

        total = int(connection.execute(
            sa_select(sa_func.count()).select_from(source).where(*conditions)
        ).scalar() or 0)
        rows = [
            dict(row)
            for row in connection.execute(
                sa_select(
                    SMILEY_FINE_TABLE.c.id,
                    SMILEY_FINE_TABLE.c.source_workbook,
                    SMILEY_FINE_TABLE.c.source_sheet,
                    SMILEY_FINE_TABLE.c.source_row_number,
                    SMILEY_FINE_TABLE.c.image_path,
                    SMILEY_FINE_TABLE.c.sku,
                    SMILEY_FINE_TABLE.c.original_sku,
                    SMILEY_FINE_TABLE.c.factory_code,
                    SMILEY_FINE_TABLE.c.factory_sku,
                    SMILEY_FINE_TABLE.c.market_price,
                    SMILEY_FINE_TABLE.c.cost,
                    SMILEY_FINE_TABLE.c.product_name,
                    SMILEY_FINE_TABLE.c.barcode,
                    SMILEY_FINE_TABLE.c.execution_standard,
                    SMILEY_FINE_TABLE.c.insole_material,
                    SMILEY_FINE_TABLE.c.outsole_material,
                    SMILEY_FINE_TABLE.c.lining_material,
                    SMILEY_FINE_TABLE.c.upper_material,
                    SMILEY_FINE_TABLE.c.shoe_box_spec,
                    SMILEY_FINE_TABLE.c.accessories,
                    SMILEY_FINE_TABLE.c.first_order_date,
                    SMILEY_FINE_TABLE.c.season_category,
                )
                .select_from(source)
                .where(*conditions)
                .order_by(SMILEY_FINE_TABLE.c.sku)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).mappings()
        ]

    return {
        "items": [_smiley_product_base_item(item, settings) for item in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "snapshot_date": snapshot_date.isoformat(),
    }


@router.get("/products")
def list_products(
    request: Request,
    brand: str = Query(...),
    query: str | None = None,
    year: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    settings = request.app.state.settings
    repository = request.app.state.repository

    if brand == "all":
        payload = repository.list_all_products(query=query, page=page, page_size=page_size)
        return {
            **payload,
            "items": [_with_brand_and_image(item, item["brand"], settings) for item in payload["items"]],
        }

    if brand == SMILEY_PRODUCT_ARCHIVE_BRAND:
        return _list_smiley_product_base_info(
            request,
            query=query,
            page=page,
            page_size=page_size,
        )

    if brand not in ALL_BRAND_KEYS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid brand: {brand}")

    payload = repository.list_products(brand, query=query, year=year, page=page, page_size=page_size)
    return {
        **payload,
        "items": [_with_brand_and_image(item, brand, settings) for item in payload["items"]],
    }


@router.get("/products/{brand}/years")
def get_product_years(request: Request, brand: str):
    if brand == SMILEY_PRODUCT_ARCHIVE_BRAND:
        return {"years": []}
    if brand == "all" or brand not in ALL_BRAND_KEYS:
        return {"years": []}
    repository = request.app.state.repository
    table = PRODUCT_TABLES[brand]
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
def list_product_color_barcodes(request: Request, brand: BrandKey):
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


@router.get("/products/{brand}/{product_id}")
def get_product(request: Request, brand: BrandKey, product_id: int):
    settings = request.app.state.settings
    item = request.app.state.repository.get_product(brand, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _with_brand_and_image(item, brand, settings)


@router.post("/products")
def create_product(request: Request, body: ProductWriteRequest):
    record = build_admin_record(body.brand, body.payload.model_dump(exclude_none=False))
    _validate_size_group(request, record.get("size_range"))
    if is_excluded_sku(record.get("sku"), record.get("original_sku")):
        raise HTTPException(status_code=400, detail="该货号已在永久排除清单中")
    item = request.app.state.repository.create_product(body.brand, record)
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(item)
    write_operation_log(
        request,
        module="product",
        action="create",
        entity_type="product",
        entity_id=item.get("id"),
        entity_label=label,
        summary=f"新增商品 {label}",
        after_data={**item, "brand": body.brand},
    )
    return {"item": {**item, "brand": body.brand}, "message": "Product created"}


@router.put("/products/{brand}/{product_id}")
def update_product(request: Request, brand: BrandKey, product_id: int, body: ProductWriteRequest):
    if body.brand != brand:
        raise HTTPException(status_code=400, detail="Brand mismatch")

    existing = request.app.state.repository.get_product(brand, product_id)
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
    item = request.app.state.repository.update_product(brand, product_id, record)
    if item is None:
        # Re-check after the pre-read in case the row was deleted concurrently.
        raise HTTPException(status_code=404, detail="Product not found")
    clear_fine_table_cache()
    clear_product_goods_cache()
    label = product_entity_label(item)
    changes = build_changed_fields(existing, item, PRODUCT_FIELD_LABELS)
    write_operation_log(
        request,
        module="product",
        action="update",
        entity_type="product",
        entity_id=product_id,
        entity_label=label,
        summary=summarize_changes("编辑商品", label, changes),
        changed_fields=changes,
        before_data={**existing, "brand": brand},
        after_data={**item, "brand": brand},
    )
    return {"item": {**item, "brand": brand}, "message": "Product updated"}


@router.delete("/products/{brand}/{product_id}")
def delete_product(request: Request, brand: BrandKey, product_id: int):
    existing = request.app.state.repository.get_product(brand, product_id)
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
        entity_id=product_id,
        entity_label=label,
        summary=f"删除商品 {label}",
        before_data={**existing, "brand": brand},
    )
    return {"message": "Product deleted"}


@router.post("/products/batch-delete")
def batch_delete_products(request: Request, body: BatchDeleteRequest):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    existing_items = request.app.state.repository.get_products_by_ids(body.brand, body.ids)
    deleted = request.app.state.repository.delete_products(body.brand, body.ids)
    clear_fine_table_cache()
    clear_product_goods_cache()
    labels = [product_entity_label(item) for item in existing_items]
    write_operation_log(
        request,
        module="product",
        action="batch_delete",
        entity_type="product",
        entity_id=",".join(str(item.get("id")) for item in existing_items),
        entity_label=f"{deleted} 条商品",
        summary=f"批量删除商品 {deleted} 条",
        before_data={"brand": body.brand, "items": existing_items[:200], "labels": labels[:200]},
    )
    return {"deleted": deleted, "message": f"已删除 {deleted} 条商品"}
