import logging

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.product_copywriting import COPYWRITING_TEMPLATE_VERSION, build_product_copywriting_prompt, product_copywriting_facts, product_facts_hash
from api.product_copywriting_jobs import lease_is_active, prepare_copywriting, run_claimed_copywriting
from api.routes.auth import user_has_permission


router = APIRouter(prefix="/product-copywriting", tags=["商品详情页文案"])
logger = logging.getLogger(__name__)


class RegenerateCopywritingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_prompt: str = Field(strict=True, min_length=1, max_length=30_000)

    @field_validator("input_prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("提示词不能为空")
        return value


def _editable_prompt(row: dict | None, item: dict) -> dict:
    if row:
        prompt = row.get("input_prompt")
        if isinstance(prompt, str) and prompt.strip():
            return {"input_prompt": prompt, "prompt_source": "saved"}
        previous = row.get("previous_result")
        prompt = previous.get("input_prompt") if isinstance(previous, dict) else None
        if isinstance(prompt, str) and prompt.strip():
            return {"input_prompt": prompt, "prompt_source": "previous"}
    try:
        prompt = build_product_copywriting_prompt(product_copywriting_facts(item))
    except HTTPException:
        return {"input_prompt": None, "prompt_source": None}
    return {"input_prompt": prompt, "prompt_source": "archive"}


def _authorized_product(request: Request, brand: str, product_id: int) -> tuple[dict, dict]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    if not user_has_permission(user, "product.view") or (
        user.get("role_code") != "super_admin" and user.get("department_code") != "美工部"
    ):
        raise HTTPException(status_code=403, detail="生图提示词仅限美工部和超级管理员使用")
    repository = request.app.state.repository
    if not repository.is_product_archive_brand(brand):
        raise HTTPException(status_code=400, detail="无效品牌")
    item = repository.get_product(brand, product_id)
    if item is None:
        raise HTTPException(status_code=404, detail="商品不存在或已删除")
    return user, item


def _run_regeneration(app, values: dict, token: str) -> None:
    settings = app.state.settings
    products = app.state.repository
    saved = app.state.product_copywriting_repository
    try:
        result = run_claimed_copywriting(settings, products, saved, values, token)
        logger.info(
            "Product copywriting regeneration finished: brand=%s product_id=%s status=%s",
            values["brand"],
            values["source_product_id"],
            result.get("status"),
        )
    except Exception:
        logger.error(
            "Product copywriting regeneration crashed: brand=%s product_id=%s",
            values["brand"],
            values["source_product_id"],
        )


def _submit_regeneration(request: Request, brand: str, product_id: int, body: RegenerateCopywritingRequest | None = None) -> JSONResponse:
    _, item = _authorized_product(request, brand, product_id)
    if not str(item.get("image_path") or "").strip():
        raise HTTPException(status_code=409, detail="该商品暂无图片，已跳过生成，已有文案保持不变")
    settings = getattr(request.app.state, "settings", None)
    saved = getattr(request.app.state, "product_copywriting_repository", None)
    executor = getattr(request.app.state, "product_copywriting_executor", None)
    slots = getattr(request.app.state, "product_copywriting_slots", None)
    if settings is None or saved is None or executor is None or slots is None:
        raise HTTPException(status_code=503, detail="提示词生成服务尚未初始化，请联系管理员")
    if not getattr(settings, "ark_api_key", None):
        raise HTTPException(status_code=503, detail="尚未配置模型密钥，请联系管理员")
    values = prepare_copywriting(settings, brand, product_id, item)
    if body is not None:
        values["input_prompt"] = body.input_prompt
    if not slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="当前生成任务较多，请稍后再试", headers={"Retry-After": "10"})
    token = None
    try:
        token = saved.claim(values, timeout_seconds=settings.doubao_timeout_seconds, force_regenerate=True)
        if token is None:
            raise HTTPException(status_code=409, detail="该商品正在生成中，请稍后刷新查看")
        future = executor.submit(_run_regeneration, request.app, values, token)
    except Exception as error:
        try:
            if token is not None:
                saved.fail(brand, product_id, token, "生成任务提交失败，请稍后重试", 503)
        finally:
            slots.release()
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(status_code=503, detail="生成任务提交失败，请稍后重试") from None

    def release_slot(completed):
        try:
            if completed.cancelled():
                saved.fail(brand, product_id, token, "服务关闭，生成任务已取消，请重试", 503)
        finally:
            slots.release()

    future.add_done_callback(release_slot)
    return JSONResponse(
        {"status": "running", "message": "正在根据提示词和商品主图重新生成，完成后自动更新。", "input_prompt": values["input_prompt"]},
        status_code=202,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{brand}/{product_id}")
def get_saved_product_copywriting(request: Request, brand: str, product_id: int = Path(gt=0)):
    _, item = _authorized_product(request, brand, product_id)
    saved = getattr(request.app.state, "product_copywriting_repository", None)
    if saved is None:
        raise HTTPException(status_code=503, detail="提示词数据库尚未初始化，请联系管理员")
    row = saved.get(brand, product_id)
    status = row["status"] if row else "missing"
    expired = status == "running" and not lease_is_active(row.get("lease_expires_at"))
    if expired:
        status = "failed"
    if row is None:
        payload = {"status": "missing", "item": None, "message": "暂无已保存的生图提示词，可点击重新生成。"}
    elif status != "completed":
        historical = row.get("previous_result")
        historical_item = None
        if isinstance(historical, dict) and historical.get("content") and historical.get("generated_at"):
            historical_item = {
                "content": historical["content"], "model": historical.get("model") or row["model"],
                "generated_at": historical["generated_at"],
                "source_updated_at": historical.get("source_updated_at") or "",
                "source_sku": historical.get("sku") or row["sku"],
                "launch_date": historical.get("launch_date") or row["launch_date"].isoformat(),
                "stale": True,
            }
        if status in {"pending", "running"}:
            message = "正在重新生成，完成后自动更新。"
        else:
            message = "生成任务已超时或中断，可点击重新生成。" if expired else "重新生成失败，可稍后重试或联系管理员检查模型服务。"
            if not expired and row.get("error_status") == 422:
                message = "商品图片不可用，请检查主图是否已关联、格式为JPEG/PNG/WebP且不超过10MB，再重新生成。"
        if historical_item:
            message += "当前保留上一版内容。"
        payload = {"status": status, "item": historical_item, "message": message}
    else:
        outdated_template = row["template_version"] != COPYWRITING_TEMPLATE_VERSION
        stale = product_facts_hash(item) != row["source_hash"] or outdated_template
        payload = {
            "status": "completed", "message": "固定提示词模板已更新，以下为旧模板保存的文案，可点击重新生成更新。" if outdated_template else "商品档案已变化，以下为此前保存的文案，上版前请核对。" if stale else "",
            "item": {
                "content": row["content"], "model": row["model"],
                "generated_at": row["generated_at"].isoformat(),
                "source_updated_at": row["source_updated_at"],
                "source_sku": row["sku"], "launch_date": row["launch_date"].isoformat(),
                "stale": stale,
            },
        }
    payload.update(_editable_prompt(row, item))
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.post("/{brand}/{product_id}/regenerate")
def regenerate_product_copywriting(request: Request, brand: str, product_id: int = Path(gt=0), body: RegenerateCopywritingRequest | None = None):
    return _submit_regeneration(request, brand, product_id, body)


@router.post("/{brand}/{product_id}", include_in_schema=False)
def retired_generate_product_copywriting(request: Request, brand: str, product_id: int = Path(gt=0)):
    _authorized_product(request, brand, product_id)
    raise HTTPException(status_code=410, detail="生图提示词已改为读取数据库，请刷新页面后查看；页面不再触发模型生成")


@router.get("/{brand}/{product_id}/jobs/{job_id}")
def get_product_copywriting_job(request: Request, brand: str, product_id: int = Path(gt=0), job_id: str = Path(pattern=r"^[a-f0-9]{32}$")):
    _authorized_product(request, brand, product_id)
    raise HTTPException(status_code=410, detail="生图提示词已改为读取数据库，请刷新页面后查看")
