from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes.images import image_url_for
from api.fine_table_cache import clear_fine_table_cache
from api.schemas import BatchDeleteRequest, BrandKey, ProductWriteRequest

from sqlalchemy import distinct as sa_distinct, select as sa_select

from domain.color_barcode_schema import COLOR_BARCODE_TABLE
from domain.excluded_skus import is_excluded_sku
from domain.schema import PRODUCT_TABLES

ALL_BRAND_KEYS = ["cbanner_mens", "cbanner_womens", "yandou", "eblan"]
PRODUCT_COLOR_BARCODE_BRANDS = {
    "cbanner_mens": "cbanner_mens",
    "cbanner_womens": "cbanner_womens",
    "yandou": "cbanner_mens",
    "eblan": "cbanner_mens",
}
from transform.rows import build_admin_record


router = APIRouter()


def _with_brand_and_image(item: dict, brand: str, settings) -> dict:
    return {
        **item,
        "brand": brand,
        "image_url": image_url_for(brand, item.get("image_path"), settings),
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
    if is_excluded_sku(record.get("sku"), record.get("original_sku")):
        raise HTTPException(status_code=400, detail="该货号已在永久排除清单中")
    item = request.app.state.repository.create_product(body.brand, record)
    clear_fine_table_cache()
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
    if is_excluded_sku(record.get("sku"), record.get("original_sku")):
        raise HTTPException(status_code=400, detail="该货号已在永久排除清单中")
    item = request.app.state.repository.update_product(brand, product_id, record)
    if item is None:
        # Re-check after the pre-read in case the row was deleted concurrently.
        raise HTTPException(status_code=404, detail="Product not found")
    clear_fine_table_cache()
    return {"item": {**item, "brand": brand}, "message": "Product updated"}


@router.delete("/products/{brand}/{product_id}")
def delete_product(request: Request, brand: BrandKey, product_id: int):
    deleted = request.app.state.repository.delete_product(brand, product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    clear_fine_table_cache()
    return {"message": "Product deleted"}


@router.post("/products/batch-delete")
def batch_delete_products(request: Request, body: BatchDeleteRequest):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    deleted = request.app.state.repository.delete_products(body.brand, body.ids)
    clear_fine_table_cache()
    return {"deleted": deleted, "message": f"已删除 {deleted} 条商品"}
