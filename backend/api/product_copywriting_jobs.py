from datetime import date, datetime, timezone

from fastapi import HTTPException

from api.product_copywriting_images import load_product_copywriting_image
from api.product_copywriting import (
    COPYWRITING_SYSTEM_PROMPT,
    COPYWRITING_TEMPLATE_VERSION,
    build_product_copywriting_prompt,
    product_copywriting_facts,
    product_facts_hash,
    request_doubao_copywriting,
    resolve_doubao_endpoint,
)


def normalized_launch_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip().replace("/", "-"))
    except ValueError:
        return None


def lease_is_active(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def prepare_copywriting(settings, brand: str, product_id: int, item: dict) -> dict:
    launch_date = normalized_launch_date(item.get("launch_date"))
    if launch_date is None:
        raise HTTPException(status_code=400, detail="商品上市日期缺失或格式不正确，请完善档案后重新生成")
    provider, endpoint = resolve_doubao_endpoint(settings)
    facts = product_copywriting_facts(item)
    return {
        "brand": brand, "source_product_id": product_id,
        "sku": str(item.get("sku") or item.get("original_sku") or ""),
        "launch_date": launch_date,
        "source_facts": facts, "source_hash": product_facts_hash(item),
        "source_updated_at": str(item.get("updated_at") or ""),
        "provider": provider, "endpoint": endpoint, "model": settings.doubao_text_model,
        "template_version": COPYWRITING_TEMPLATE_VERSION,
        "input_prompt": build_product_copywriting_prompt(facts),
        "system_prompt": COPYWRITING_SYSTEM_PROMPT,
        "input_image": {"path": str(item.get("image_path") or "").strip()},
    }


def run_claimed_copywriting(settings, products, saved, values: dict, token: str) -> dict:
    brand, product_id = values["brand"], values["source_product_id"]
    result = {"brand": brand, "product_id": product_id, "sku": values["sku"], "launch_date": str(values["launch_date"])}

    def validate_product() -> dict:
        current = products.get_product(brand, product_id)
        if (
            current is None
            or normalized_launch_date(current.get("launch_date")) != values["launch_date"]
            or product_facts_hash(current) != values["source_hash"]
        ):
            raise HTTPException(status_code=409, detail="生成期间商品资料或上市日期发生变化，未保存旧资料文案")
        return current

    try:
        claimed = saved.get(brand, product_id)
        if claimed is None or claimed["status"] != "running" or claimed["claim_token"] != token:
            return {**result, "status": "superseded"}
        if not lease_is_active(claimed["lease_expires_at"]):
            raise HTTPException(status_code=504, detail="生成任务已过期，请重新生成")
        current = validate_product()
        image = load_product_copywriting_image(settings, brand, current)
        validate_product()
        if not saved.record_input_image(brand, product_id, token, {**values["input_image"], **image.metadata()}):
            return {**result, "status": "superseded"}
        content = request_doubao_copywriting(settings, values["input_prompt"], image_data_url=image.data_url)
        validate_product()
        if not saved.complete(brand, product_id, token, content):
            return {**result, "status": "superseded"}
        return {**result, "status": "completed", "characters": len(content)}
    except HTTPException as error:
        saved.fail(brand, product_id, token, str(error.detail), error.status_code)
        return {**result, "status": "failed", "error_status": error.status_code, "error": str(error.detail)}
    except Exception:
        saved.fail(brand, product_id, token, "生成内部错误，请联系管理员后重试", 500)
        return {**result, "status": "failed", "error_status": 500}
