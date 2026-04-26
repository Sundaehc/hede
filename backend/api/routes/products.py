from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.routes.images import image_url_for
from api.schemas import BrandKey, ProductWriteRequest
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
    brand: BrandKey = Query(...),
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    settings = request.app.state.settings
    payload = request.app.state.repository.list_products(brand, query=query, page=page, page_size=page_size)
    return {
        **payload,
        "items": [_with_brand_and_image(item, brand, settings) for item in payload["items"]],
    }


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
    item = request.app.state.repository.create_product(body.brand, record)
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
    item = request.app.state.repository.update_product(brand, product_id, record)
    if item is None:
        # Re-check after the pre-read in case the row was deleted concurrently.
        raise HTTPException(status_code=404, detail="Product not found")
    return {"item": {**item, "brand": brand}, "message": "Product updated"}


@router.delete("/products/{brand}/{product_id}")
def delete_product(request: Request, brand: BrandKey, product_id: int):
    deleted = request.app.state.repository.delete_product(brand, product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted"}
