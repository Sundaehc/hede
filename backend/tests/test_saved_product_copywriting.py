import base64
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import Future
from threading import BoundedSemaphore

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, create_engine, inspect, select, update
from sqlalchemy.pool import StaticPool

from api.auth_middleware import auth_middleware
from api import product_copywriting_jobs as jobs
from api import product_copywriting_images as images
from api.product_copywriting import COPYWRITING_SYSTEM_PROMPT, COPYWRITING_TEMPLATE_VERSION, build_product_copywriting_prompt, product_copywriting_facts, product_facts_hash
from api.routes.product_copywriting import router
from domain.product_copywriting_schema import PRODUCT_COPYWRITING_HISTORY_TABLE, PRODUCT_COPYWRITING_TABLE
from scripts import generate_product_copywriting as batch
from storage.product_copywriting_repository import ProductCopywritingRepository


IMAGE_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aQ3sAAAAASUVORK5CYII=")
IMAGE_DATA_URL = "data:image/png;base64," + base64.b64encode(IMAGE_BYTES).decode("ascii")


class DeferredExecutor:
    def __init__(self):
        self.tasks = []

    def submit(self, function, *args):
        future = Future()
        self.tasks.append((future, function, args))
        return future

    def run_next(self):
        future, function, args = self.tasks.pop(0)
        future.set_result(function(*args))

    def shutdown(self, **kwargs):
        for future, _, _ in self.tasks:
            future.cancel()
        self.tasks.clear()


@pytest.fixture
def saved():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    repository = ProductCopywritingRepository(engine)
    repository.create_tables()
    yield repository
    engine.dispose()


@pytest.fixture
def product(tmp_path):
    image_path = tmp_path / "RM363238D45.png"
    image_path.write_bytes(IMAGE_BYTES)
    return {"id": 7, "sku": "RM363238D45", "launch_date": "2026-09-20", "color": "灰色", "cost": "999", "supplier_name": "内部供应商", "updated_at": "2026-09-21", "image_path": str(image_path)}


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(ark_api_key="test-secret", doubao_provider="custom", doubao_base_url="https://model.pardx.cn", doubao_text_model="doubao-seed-pro", doubao_timeout_seconds=180, image_roots={"cbanner": tmp_path})


def saved_values(product):
    return {
        "brand": "cbanner_womens", "source_product_id": product["id"], "sku": product["sku"],
        "launch_date": date(2026, 9, 20), "source_facts": {"颜色": "灰色"}, "source_hash": product_facts_hash(product),
        "source_updated_at": product["updated_at"], "provider": "custom", "model": "doubao-seed-pro", "endpoint": "https://model.pardx.cn/v1/chat/completions", "template_version": COPYWRITING_TEMPLATE_VERSION,
        "input_prompt": build_product_copywriting_prompt(product_copywriting_facts(product)), "system_prompt": COPYWRITING_SYSTEM_PROMPT,
    }


def test_table_creation_is_idempotent_and_completed_rows_survive_new_repository(saved, product):
    values = saved_values(product)
    token = saved.claim(values, timeout_seconds=180)
    assert token
    assert saved.claim(values, timeout_seconds=180) is None
    assert saved.complete("cbanner_womens", 7, token, "真实模型结果")
    saved.create_tables()
    reopened = ProductCopywritingRepository(saved.engine)
    assert reopened.get("cbanner_womens", 7)["content"] == "真实模型结果"
    assert reopened.claim(values, timeout_seconds=180, retry_failed=True) is None
    assert reopened.get("cbanner_womens", 7)["attempt_count"] == 1
    assert reopened.get("eblan", 7) is None


def test_failed_rows_require_explicit_retry_and_old_claim_cannot_overwrite(saved, product):
    values = saved_values(product)
    first = saved.claim(values, timeout_seconds=180)
    assert saved.fail("cbanner_womens", 7, first, "超时", 504)
    assert saved.claim(values, timeout_seconds=180) is None
    second = saved.claim(values, timeout_seconds=180, retry_failed=True)
    assert second and second != first
    assert not saved.complete("cbanner_womens", 7, first, "旧结果")
    assert saved.complete("cbanner_womens", 7, second, "重试成功")
    assert saved.get("cbanner_womens", 7)["attempt_count"] == 2
    assert saved.get("cbanner_womens", 7)["last_error"] is None


def test_legacy_table_migration_adds_prompt_columns_without_losing_rows(product):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    legacy = PRODUCT_COPYWRITING_TABLE.to_metadata(metadata)
    for name in ("input_prompt", "system_prompt", "input_image", "previous_result"):
        legacy._columns.remove(legacy.c[name])
    metadata.create_all(engine)
    values = saved_values(product)
    values.pop("input_prompt")
    values.pop("system_prompt")
    with engine.begin() as connection:
        connection.execute(legacy.insert().values(**values, status="completed", content="历史正文", generated_at=datetime.now(timezone.utc)))
    repository = ProductCopywritingRepository(engine)
    repository.create_tables()
    repository.create_tables()
    assert {"input_prompt", "system_prompt", "input_image", "previous_result"} <= {column["name"] for column in inspect(engine).get_columns("product_copywriting")}
    assert repository.get("cbanner_womens", 7)["content"] == "历史正文"
    engine.dispose()


def test_template_refresh_is_explicit_backs_up_previous_result_and_skips_current(saved, product):
    old_values = {**saved_values(product), "template_version": "old-template", "input_prompt": "旧输入"}
    old_token = saved.claim(old_values, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, old_token, "旧模板正文")
    current_values = saved_values(product)
    assert saved.claim(current_values, timeout_seconds=180, retry_failed=True) is None
    current_token = saved.claim(current_values, timeout_seconds=180, refresh_outdated_template=True)
    row = saved.get("cbanner_womens", 7)
    assert row["content"] is None
    assert row["generated_at"] is None
    assert row["previous_result"]["content"] == "旧模板正文"
    assert row["previous_result"]["input_prompt"] == "旧输入"
    assert row["input_prompt"] == current_values["input_prompt"]
    assert not saved.complete("cbanner_womens", 7, old_token, "旧任务迟到结果")
    saved.fail("cbanner_womens", 7, current_token, "超时", 504)
    assert saved.get("cbanner_womens", 7)["previous_result"]["content"] == "旧模板正文"
    assert saved.claim(current_values, timeout_seconds=180, refresh_outdated_template=True) is None
    retry_token = saved.claim(current_values, timeout_seconds=180, retry_failed=True)
    saved.complete("cbanner_womens", 7, retry_token, "新模板正文")
    assert saved.claim(current_values, timeout_seconds=180, refresh_outdated_template=True, retry_failed=True) is None
    assert saved.get("cbanner_womens", 7)["previous_result"]["content"] == "旧模板正文"


def test_template_refresh_cannot_steal_active_lease(saved, product):
    old_token = saved.claim({**saved_values(product), "template_version": "old-template"}, timeout_seconds=180)
    assert saved.claim(saved_values(product), timeout_seconds=180, refresh_outdated_template=True) is None
    with saved.engine.begin() as connection:
        connection.execute(update(PRODUCT_COPYWRITING_TABLE).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    assert saved.claim(saved_values(product), timeout_seconds=180, refresh_outdated_template=True)
    assert not saved.complete("cbanner_womens", 7, old_token, "旧任务迟到结果")


def test_expired_lease_is_only_reclaimed_on_explicit_retry(saved, product):
    values = saved_values(product)
    saved.claim(values, timeout_seconds=180)
    assert saved.claim(values, timeout_seconds=180, retry_failed=True) is None
    with saved.engine.begin() as connection:
        connection.execute(update(PRODUCT_COPYWRITING_TABLE).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    assert saved.claim(values, timeout_seconds=180) is None
    assert saved.claim(values, timeout_seconds=180, retry_failed=True)


def test_batch_only_selects_exact_target_dates_active_unexcluded_products(saved, monkeypatch):
    metadata = MetaData()
    table = Table("products", metadata, Column("id", Integer, primary_key=True), Column("sku", Text), Column("original_sku", Text), Column("launch_date", Text), Column("deleted_at", DateTime))
    metadata.create_all(saved.engine)
    dates = ["2026-09-19", "2026-09-20", "2026-09-21", "2026-09-22", "2026/09/20", "2026-09-210", "2026-09-20", "2026-09-21"]
    with saved.engine.begin() as connection:
        connection.execute(table.insert(), [{"id": index, "sku": str(index), "launch_date": day, "deleted_at": datetime.now() if index == 6 else None} for index, day in enumerate(dates)])
    monkeypatch.setattr(batch, "not_excluded_sku_condition", lambda *columns: columns[0] != "7")
    products = SimpleNamespace(engine=saved.engine, product_archive_brands=lambda: ["brand"], _table_for_brand=lambda brand: table)
    assert [item["id"] for brand, item in batch.target_products(products)] == [1, 2, 4]


@pytest.mark.parametrize("launch_date", ["2026-09-19", "2026-09-22", None, "2026-09-210"])
def test_batch_outside_dates_never_calls_model_or_inserts(saved, settings, product, launch_date, monkeypatch):
    product["launch_date"] = launch_date
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["status"] == "outside_scope"
    assert saved.get("cbanner_womens", 7) is None
    model.assert_not_called()


def test_batch_saves_actual_model_content_once_and_only_safe_facts(saved, settings, product, monkeypatch):
    model = Mock(return_value="模型真实输出正文")
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["status"] == "completed"
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["status"] == "skipped"
    row = saved.get("cbanner_womens", 7)
    assert row["content"] == "模型真实输出正文"
    assert row["launch_date"] == date(2026, 9, 20)
    assert "内部供应商" not in str(row["source_facts"])
    assert "999" not in str(row["source_facts"])
    assert row["input_prompt"] == build_product_copywriting_prompt(product_copywriting_facts(product))
    assert row["system_prompt"] == COPYWRITING_SYSTEM_PROMPT
    assert row["template_version"] == COPYWRITING_TEMPLATE_VERSION
    model.assert_called_once_with(settings, row["input_prompt"], image_data_url=IMAGE_DATA_URL)
    assert row["input_image"] == {
        "archive_path": product["image_path"], "sha256": hashlib.sha256(IMAGE_BYTES).hexdigest(),
        "media_type": "image/png", "size_bytes": len(IMAGE_BYTES),
        "source": "local", "transport": "base64_data_url",
        "us3_object_key": None, "fallback_reason": "us3_not_configured",
    }


def test_prepared_image_does_not_claim_a_source_before_loading(settings, product):
    values = jobs.prepare_copywriting(settings, "cbanner_womens", 7, product)
    assert values["input_image"] == {"archive_path": product["image_path"]}


@pytest.mark.parametrize("model_fails", [False, True])
def test_cloud_image_provenance_is_saved_before_model_call_and_legacy_backup_survives(saved, settings, product, monkeypatch, model_fails):
    legacy_image = {"path": product["image_path"], "sha256": "legacy-hash"}
    token = saved.claim({**saved_values(product), "input_image": legacy_image, "template_version": "legacy"}, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧文案")
    settings.ucloud_us3_configured = True
    storage = Mock()
    storage.object_key.return_value = "cbanner_womens/RM363238D45.png"
    storage.has_synced_object.return_value = True
    storage.private_download_url.return_value = "https://example.test/image?signature=private"
    monkeypatch.setattr(images.UCloudUS3ImageStorage, "from_settings", Mock(return_value=storage))
    monkeypatch.setattr(images._image_opener, "open", Mock(return_value=io.BytesIO(IMAGE_BYTES)))
    def generate(*args, **kwargs):
        image_record = saved.get("cbanner_womens", 7)["input_image"]
        assert image_record["archive_path"] == product["image_path"]
        assert image_record["source"] == "us3"
        assert image_record["transport"] == "base64_data_url"
        assert image_record["us3_object_key"] == "cbanner_womens/RM363238D45.png"
        assert image_record["fallback_reason"] is None
        assert "path" not in image_record
        assert kwargs["image_data_url"] == IMAGE_DATA_URL
        if model_fails:
            raise HTTPException(status_code=504, detail="模型超时")
        return "新文案"
    model = Mock(side_effect=generate)
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    result = batch.generate_one(settings, products, saved, "cbanner_womens", 7, refresh_outdated_template=True)
    assert result["status"] == ("failed" if model_fails else "completed")
    row = saved.get("cbanner_womens", 7)
    assert row["previous_result"]["input_image"] == legacy_image
    assert row["previous_result"]["content"] == "旧文案"
    assert row["input_image"]["source"] == "us3"
    assert "signature" not in json.dumps(row["input_image"])
    assert IMAGE_DATA_URL not in json.dumps(row["input_image"])
    model.assert_called_once()


def test_batch_records_failure_without_fabricating_content(saved, settings, product, monkeypatch):
    monkeypatch.setattr(jobs, "request_doubao_copywriting", Mock(side_effect=HTTPException(504, "模型超时")))
    products = Mock(get_product=Mock(return_value=product))
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["status"] == "failed"
    row = saved.get("cbanner_womens", 7)
    assert row["content"] is None
    assert row["status"] == "failed"
    assert row["error_status"] == 504


def test_changed_product_during_generation_is_not_saved(saved, settings, product, monkeypatch):
    products = Mock(get_product=Mock(side_effect=[product, product, product, {**product, "color": "黑色"}]))
    monkeypatch.setattr(jobs, "request_doubao_copywriting", Mock(return_value="旧资料生成内容"))
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["error_status"] == 409
    assert saved.get("cbanner_womens", 7)["content"] is None


@pytest.fixture
def client(saved, product, settings):
    app = FastAPI()
    app.state.repository = Mock(is_product_archive_brand=Mock(return_value=True), get_product=Mock(return_value=product))
    app.state.product_copywriting_repository = saved
    app.state.settings = settings
    app.state.product_copywriting_executor = DeferredExecutor()
    app.state.product_copywriting_slots = BoundedSemaphore(2)
    user = {"id": 42, "department_code": "美工部", "role_code": "design_viewer", "permissions": ["product.view"]}
    app.state.auth_repository = Mock(has_users=Mock(return_value=True), get_user_by_session=Mock(return_value=user))
    app.middleware("http")(auth_middleware)
    app.include_router(router)
    with TestClient(app) as http:
        yield SimpleNamespace(http=http, user=user, app=app)
    executor = app.state.product_copywriting_executor
    if hasattr(executor, "shutdown"):
        executor.shutdown(wait=True)


def test_regenerate_claims_before_enqueue_and_blocks_duplicate_requests(client, saved, product, monkeypatch):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "上一版内容")
    model = Mock(return_value="新生成内容")
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    response = client.http.post("/product-copywriting/cbanner_womens/7/regenerate")
    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert response.headers["cache-control"] == "no-store"
    assert saved.get("cbanner_womens", 7)["status"] == "running"
    model.assert_not_called()
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 409
    assert len(client.app.state.product_copywriting_executor.tasks) == 1
    running = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert running["status"] == "running"
    assert running["item"]["content"] == "上一版内容"
    client.app.state.product_copywriting_executor.run_next()
    completed = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert completed["status"] == "completed"
    assert completed["item"]["content"] == "新生成内容"
    assert completed["item"]["stale"] is False
    row = saved.get("cbanner_womens", 7)
    model.assert_called_once_with(client.app.state.settings, row["input_prompt"], image_data_url=IMAGE_DATA_URL)
    assert row["previous_result"]["content"] == "上一版内容"
    assert row["attempt_count"] == 2
    client.user["department_code"] = "财务部"
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 403


def test_regenerate_rejects_active_job_and_missing_launch_date(client, saved, product):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 409
    saved.fail("cbanner_womens", 7, token, "测试", 500)
    product["launch_date"] = None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 400


def test_regeneration_failure_keeps_previous_content_visible(client, saved, product, monkeypatch):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "上一版内容")
    model = Mock(side_effect=HTTPException(504, "测试模型超时"))
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    response = client.http.post("/product-copywriting/cbanner_womens/7/regenerate")
    assert response.status_code == 202
    client.app.state.product_copywriting_executor.run_next()
    refreshed = client.http.get("/product-copywriting/cbanner_womens/7")
    assert refreshed.json()["item"]["content"] == "上一版内容"
    assert refreshed.json()["status"] == "failed"
    assert "测试模型超时" not in refreshed.text
    assert saved.get("cbanner_womens", 7)["content"] is None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    assert saved.get("cbanner_womens", 7)["previous_result"]["content"] == "上一版内容"


@pytest.mark.parametrize("launch_date", ["2026-09-19", "2026-09-22"])
def test_manual_regeneration_other_dates_is_explicit_and_not_a_batch(client, saved, product, launch_date, monkeypatch):
    product["launch_date"] = launch_date
    model = Mock(return_value="手动生成内容")
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    assert client.http.get("/product-copywriting/cbanner_womens/7").json()["status"] == "missing"
    assert saved.get("cbanner_womens", 7) is None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    client.app.state.product_copywriting_executor.run_next()
    assert str(saved.get("cbanner_womens", 7)["launch_date"]) == launch_date
    model.assert_called_once()


def test_regeneration_queue_failure_restores_access_to_previous_content(client, saved, product):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧正文")
    client.app.state.product_copywriting_executor.submit = Mock(side_effect=RuntimeError("private-error"))
    response = client.http.post("/product-copywriting/cbanner_womens/7/regenerate")
    assert response.status_code == 503
    assert "private-error" not in response.text
    assert saved.get("cbanner_womens", 7)["status"] == "failed"
    assert client.http.get("/product-copywriting/cbanner_womens/7").json()["item"]["content"] == "旧正文"
    slots = client.app.state.product_copywriting_slots
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    slots.release()
    slots.release()


def test_regeneration_capacity_is_bounded_and_cancel_releases_slots(client, saved):
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    assert client.http.post("/product-copywriting/cbanner_womens/8/regenerate").status_code == 202
    assert client.http.post("/product-copywriting/cbanner_womens/9/regenerate").status_code == 429
    assert saved.get("cbanner_womens", 9) is None
    client.app.state.product_copywriting_executor.shutdown()
    assert saved.get("cbanner_womens", 7)["status"] == "failed"
    assert client.http.post("/product-copywriting/cbanner_womens/9/regenerate").status_code == 202


def test_regeneration_checks_config_and_auth_before_writing(client, saved, product):
    client.app.state.settings.ark_api_key = None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 503
    client.app.state.settings.ark_api_key = "test-secret"
    client.user["permissions"] = []
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 403
    client.user["permissions"] = ["product.view"]
    client.app.state.repository.get_product.return_value = None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 404
    client.app.state.repository.get_product.return_value = product
    client.app.state.auth_repository.get_user_by_session.return_value = None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 401
    assert saved.get("cbanner_womens", 7) is None


def test_superadmin_regeneration_and_expired_lease_recovery(client, saved, product, monkeypatch):
    client.user.update(role_code="super_admin", department_code="财务部")
    old_token = saved.claim(saved_values(product), timeout_seconds=180)
    with saved.engine.begin() as connection:
        connection.execute(update(PRODUCT_COPYWRITING_TABLE).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    assert client.http.get("/product-copywriting/cbanner_womens/7").json()["status"] == "failed"
    assert saved.get("cbanner_womens", 7)["status"] == "running"
    monkeypatch.setattr(jobs, "request_doubao_copywriting", Mock(return_value="恢复成功"))
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    assert not saved.complete("cbanner_womens", 7, old_token, "过期任务结果")
    client.app.state.product_copywriting_executor.run_next()
    assert saved.get("cbanner_womens", 7)["content"] == "恢复成功"


@pytest.mark.parametrize("change", [{"launch_date": "2026-09-21"}, {"color": "黑色"}, {"image_path": "another-image.png"}])
def test_regeneration_does_not_save_when_product_changes(client, saved, product, monkeypatch, change):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧正文")
    def model(*args, **kwargs):
        product.update(change)
        return "不应保存的新正文"
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    client.app.state.product_copywriting_executor.run_next()
    row = saved.get("cbanner_womens", 7)
    assert row["error_status"] == 409
    assert row["content"] is None
    assert row["previous_result"]["content"] == "旧正文"


def test_changed_product_before_worker_start_never_calls_model(client, saved, product, monkeypatch):
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    product["color"] = "黑色"
    client.app.state.product_copywriting_executor.run_next()
    model.assert_not_called()
    assert saved.get("cbanner_womens", 7)["status"] == "failed"


def test_image_failure_preserves_previous_copy_without_model_call(client, saved, product, monkeypatch):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧正文继续展示")
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    Path(product["image_path"]).write_bytes(b"not an image")
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate").status_code == 202
    client.app.state.product_copywriting_executor.run_next()
    model.assert_not_called()
    row = saved.get("cbanner_womens", 7)
    assert row["status"] == "failed"
    assert row["error_status"] == 422
    response = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert response["item"]["content"] == "旧正文继续展示"
    assert "图片" in response["message"]


@pytest.mark.parametrize("image_path", [None, "", " \t "])
@pytest.mark.parametrize("existing_status", [None, "completed", "failed"])
def test_batch_skips_no_image_without_changing_database(saved, settings, product, monkeypatch, image_path, existing_status):
    if existing_status:
        token = saved.claim(saved_values(product), timeout_seconds=180)
        if existing_status == "completed":
            saved.complete("cbanner_womens", 7, token, "旧文案")
        else:
            saved.fail("cbanner_womens", 7, token, "之前的错误", 504)
    before = saved.get("cbanner_womens", 7)
    product["image_path"] = image_path
    model = Mock()
    loader = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    monkeypatch.setattr(jobs, "load_product_copywriting_image", loader)
    products = Mock(get_product=Mock(return_value=product))
    result = batch.generate_one(settings, products, saved, "cbanner_womens", 7, retry_failed=True, refresh_outdated_template=True)
    assert result["status"] == "skipped"
    assert result["reason"] == "missing_image"
    assert saved.get("cbanner_womens", 7) == before
    model.assert_not_called()
    loader.assert_not_called()


@pytest.mark.parametrize("image_path", [None, "", " \t "])
@pytest.mark.parametrize("existing", [False, True])
def test_manual_no_image_never_claims_or_enqueues(client, saved, product, image_path, existing):
    if existing:
        token = saved.claim(saved_values(product), timeout_seconds=180)
        saved.complete("cbanner_womens", 7, token, "旧文案")
    before = saved.get("cbanner_womens", 7)
    product["image_path"] = image_path
    response = client.http.post("/product-copywriting/cbanner_womens/7/regenerate")
    assert response.status_code == 409
    assert "已跳过" in response.json()["detail"]
    assert client.app.state.product_copywriting_executor.tasks == []
    assert saved.get("cbanner_womens", 7) == before
    slots = client.app.state.product_copywriting_slots
    assert slots.acquire(blocking=False) and slots.acquire(blocking=False)
    slots.release()
    slots.release()


def test_image_path_change_during_loading_prevents_model_call(saved, settings, product, monkeypatch):
    loader = jobs.load_product_copywriting_image
    def change_image(*args):
        image = loader(*args)
        product["image_path"] = "changed.png"
        return image
    monkeypatch.setattr(jobs, "load_product_copywriting_image", change_image)
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["error_status"] == 409
    model.assert_not_called()


def test_image_metadata_is_token_guarded_and_backed_up(saved, product):
    values = saved_values(product)
    token = saved.claim(values, timeout_seconds=180)
    metadata = {"path": product["image_path"], "sha256": "first-image"}
    assert not saved.record_input_image("cbanner_womens", 7, "wrong-token", metadata)
    assert saved.record_input_image("cbanner_womens", 7, token, metadata)
    saved.complete("cbanner_womens", 7, token, "旧正文")
    next_token = saved.claim({**values, "input_image": {"path": "new.png"}}, timeout_seconds=180, force_regenerate=True)
    assert next_token != token
    row = saved.get("cbanner_womens", 7)
    assert row["previous_result"]["input_image"] == metadata
    assert not saved.record_input_image("cbanner_womens", 7, token, metadata)
    assert row["input_image"] == {"path": "new.png"}


def test_expired_job_cannot_record_image_or_call_model(saved, settings, product, monkeypatch):
    loader = jobs.load_product_copywriting_image
    def expire_job(*args):
        image = loader(*args)
        with saved.engine.begin() as connection:
            connection.execute(update(PRODUCT_COPYWRITING_TABLE).values(lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        return image
    monkeypatch.setattr(jobs, "load_product_copywriting_image", expire_job)
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    products = Mock(get_product=Mock(return_value=product))
    assert batch.generate_one(settings, products, saved, "cbanner_womens", 7)["status"] == "superseded"
    model.assert_not_called()


def test_image_column_migration_keeps_current_table_content_and_previous_result(product):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    legacy = PRODUCT_COPYWRITING_TABLE.to_metadata(metadata)
    legacy._columns.remove(legacy.c.input_image)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(legacy.insert().values(
            **saved_values(product), status="completed", content="已存纯文字结果",
            previous_result={"content": "更早一版结果"}, generated_at=datetime.now(timezone.utc),
        ))
    repository = ProductCopywritingRepository(engine)
    repository.create_tables()
    repository.create_tables()
    row = repository.get("cbanner_womens", 7)
    assert row["content"] == "已存纯文字结果"
    assert row["previous_result"] == {"content": "更早一版结果"}
    assert row["input_image"] is None
    engine.dispose()


def test_get_saved_content_never_loads_images_or_exposes_image_metadata(client, saved, product, monkeypatch):
    token = saved.claim({**saved_values(product), "input_image": {"path": "private-path", "sha256": "private-hash"}}, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "已有正文")
    loader = Mock(side_effect=AssertionError("GET must only read database"))
    monkeypatch.setattr(jobs, "load_product_copywriting_image", loader)
    response = client.http.get("/product-copywriting/cbanner_womens/7")
    assert response.json()["item"]["content"] == "已有正文"
    assert "input_image" not in response.text
    assert "private-" not in response.text
    loader.assert_not_called()


def test_read_endpoint_only_reads_saved_content_without_api_key(client, saved, product):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "已存数据库的内容")
    response = client.http.get("/product-copywriting/cbanner_womens/7")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["item"]["content"] == "已存数据库的内容"
    assert response.json()["item"]["stale"] is False
    assert "source_facts" not in response.text
    assert "endpoint" not in response.text
    assert saved.get("cbanner_womens", 7)["attempt_count"] == 1


def test_missing_record_returns_empty_and_does_not_create_one(client, saved):
    response = client.http.get("/product-copywriting/cbanner_womens/7")
    assert response.json()["status"] == "missing"
    assert response.json()["item"] is None
    assert saved.get("cbanner_womens", 7) is None


def test_old_template_is_marked_but_get_never_triggers_regeneration(client, saved, product):
    token = saved.claim({**saved_values(product), "template_version": "old-template"}, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧文案")
    response = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert response["item"]["content"] == "旧文案"
    assert response["item"]["stale"] is True
    assert "旧模板" in response["message"]
    assert saved.get("cbanner_womens", 7)["attempt_count"] == 1


def test_running_failed_and_stale_content_display_states(client, saved, product):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    assert client.http.get("/product-copywriting/cbanner_womens/7").json()["status"] == "running"
    saved.fail("cbanner_womens", 7, token, "internal-message", 502)
    response = client.http.get("/product-copywriting/cbanner_womens/7")
    assert response.json()["status"] == "failed"
    assert "internal-message" not in response.text
    token = saved.claim(saved_values(product), timeout_seconds=180, retry_failed=True)
    saved.complete("cbanner_womens", 7, token, "已保存")
    product["color"] = "黑色"
    response = client.http.get("/product-copywriting/cbanner_womens/7")
    assert response.json()["item"]["stale"] is True
    assert response.json()["item"]["content"] == "已保存"


@pytest.mark.parametrize("department", ["财务部", "客服部", "商品部", "运营部", "开发部"])
def test_saved_content_still_requires_design_department(client, department):
    client.user["department_code"] = department
    assert client.http.get("/product-copywriting/cbanner_womens/7").status_code == 403


def test_saved_content_requires_auth_view_and_active_product(client):
    client.user["permissions"] = []
    assert client.http.get("/product-copywriting/cbanner_womens/7").status_code == 403
    client.user["permissions"] = ["product.view"]
    client.app.state.repository.get_product.return_value = None
    assert client.http.get("/product-copywriting/cbanner_womens/7").status_code == 404
    client.app.state.auth_repository.get_user_by_session.return_value = None
    assert client.http.get("/product-copywriting/cbanner_womens/7").status_code == 401


def test_legacy_generation_urls_do_not_generate_or_insert(client, saved):
    assert client.http.post("/product-copywriting/cbanner_womens/7", json={"regenerate": True}).status_code == 410
    assert client.http.get("/product-copywriting/cbanner_womens/7/jobs/" + "a" * 32).status_code == 410
    assert saved.get("cbanner_womens", 7) is None


def test_saved_prompt_is_exposed_exactly_without_internal_configuration(client, saved, product, monkeypatch):
    values = {**saved_values(product), "input_prompt": "  历史提示词\n保留换行与空格  ", "system_prompt": "内部系统规则"}
    token = saved.claim(values, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "历史正文")
    before = saved.get("cbanner_womens", 7)
    model = Mock()
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    client.app.state.settings.ark_api_key = None
    response = client.http.get("/product-copywriting/cbanner_womens/7")
    assert response.json()["input_prompt"] == values["input_prompt"]
    assert response.json()["prompt_source"] == "saved"
    assert response.json()["item"]["content"] == "历史正文"
    for private_field in ("内部系统规则", "system_prompt", "test-secret", "endpoint", "input_image"):
        assert private_field not in response.text
    assert saved.get("cbanner_womens", 7) == before
    model.assert_not_called()


def test_edited_prompt_is_persisted_and_sent_exactly_with_the_product_image(client, saved, product, monkeypatch):
    values = saved_values(product)
    token = saved.claim(values, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "上一版正文")
    edited_prompt = "  修改后的完整提示词\n以通勤搭配为主，保留六个区块。  "
    model = Mock(return_value="按编辑内容生成的新版正文")
    monkeypatch.setattr(jobs, "request_doubao_copywriting", model)
    response = client.http.post("/product-copywriting/cbanner_womens/7/regenerate", json={"input_prompt": edited_prompt})
    assert response.status_code == 202
    assert response.json()["input_prompt"] == edited_prompt
    running = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert running["input_prompt"] == edited_prompt
    assert running["item"]["content"] == "上一版正文"
    model.assert_not_called()
    client.app.state.product_copywriting_executor.run_next()
    model.assert_called_once_with(client.app.state.settings, edited_prompt, image_data_url=IMAGE_DATA_URL)
    row = saved.get("cbanner_womens", 7)
    assert row["input_prompt"] == edited_prompt
    assert row["system_prompt"] == COPYWRITING_SYSTEM_PROMPT
    assert row["previous_result"]["input_prompt"] == values["input_prompt"]
    completed = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert completed["input_prompt"] == edited_prompt
    assert completed["item"]["content"] == "按编辑内容生成的新版正文"


def test_failed_custom_prompt_remains_editable_with_previous_content(client, saved, product, monkeypatch):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "保留旧正文")
    monkeypatch.setattr(jobs, "request_doubao_copywriting", Mock(side_effect=HTTPException(504, "模型超时")))
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate", json={"input_prompt": "待重试的编辑提示词"}).status_code == 202
    client.app.state.product_copywriting_executor.run_next()
    response = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert response["status"] == "failed"
    assert response["input_prompt"] == "待重试的编辑提示词"
    assert response["prompt_source"] == "saved"
    assert response["item"]["content"] == "保留旧正文"


@pytest.mark.parametrize("body", [
    {"input_prompt": ""}, {"input_prompt": " \n\t"}, {"input_prompt": "字" * 30_001},
    {"input_prompt": None}, {"input_prompt": 123}, {"input_prompt": []}, {},
    {"input_prompt": "修改", "system_prompt": "替换系统规则"},
    {"input_prompt": "修改", "image_url": "https://external.test/image.png"},
])
def test_invalid_edited_prompt_never_claims_or_enqueues(client, saved, product, body):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "不应改动")
    before = saved.get("cbanner_womens", 7)
    response = client.http.post("/product-copywriting/cbanner_womens/7/regenerate", json=body)
    assert response.status_code == 422
    assert saved.get("cbanner_womens", 7) == before
    assert client.app.state.product_copywriting_executor.tasks == []


def test_edited_prompt_still_requires_design_permission_and_product_image(client, saved, product):
    client.user["department_code"] = "财务部"
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate", json={"input_prompt": "修改"}).status_code == 403
    client.user["department_code"] = "美工部"
    product["image_path"] = None
    assert client.http.post("/product-copywriting/cbanner_womens/7/regenerate", json={"input_prompt": "修改"}).status_code == 409
    assert saved.get("cbanner_womens", 7) is None
    assert client.app.state.product_copywriting_executor.tasks == []


@pytest.mark.parametrize("historical_prompt", [None, "", " \t "])
def test_legacy_missing_prompt_uses_labeled_archive_fallback_without_replacing_old_content(client, saved, product, historical_prompt):
    token = saved.claim({**saved_values(product), "input_prompt": historical_prompt}, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "没有输入记录的旧正文")
    before = saved.get("cbanner_womens", 7)
    response = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert response["input_prompt"] == build_product_copywriting_prompt(product_copywriting_facts(product))
    assert response["prompt_source"] == "archive"
    assert response["item"]["content"] == "没有输入记录的旧正文"
    assert saved.get("cbanner_womens", 7) == before


def test_missing_record_preview_only_fills_prompt_without_model_configuration(client, saved, product):
    client.app.state.settings = None
    response = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert response["status"] == "missing"
    assert response["input_prompt"] == build_product_copywriting_prompt(product_copywriting_facts(product))
    assert response["prompt_source"] == "archive"
    assert saved.get("cbanner_womens", 7) is None


def test_previous_prompt_is_used_when_latest_record_has_none(client, saved, product):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧正文")
    saved.claim({**saved_values(product), "input_prompt": None}, timeout_seconds=180, force_regenerate=True)
    response = client.http.get("/product-copywriting/cbanner_womens/7").json()
    assert response["input_prompt"] == saved_values(product)["input_prompt"]
    assert response["prompt_source"] == "previous"
    assert response["item"]["content"] == "旧正文"


def test_history_keeps_all_successful_versions_and_skips_failures(saved, product):
    values = saved_values(product)
    for index in range(4):
        token = saved.claim({**values, "input_prompt": f"输入{index}"}, timeout_seconds=180, force_regenerate=True)
        assert saved.complete("cbanner_womens", 7, token, f"正文{index}")
        assert not saved.complete("cbanner_womens", 7, token, "迟到重复结果")
    rows = saved.list_history("cbanner_womens", 7)
    assert len(rows) == 4
    assert [saved.get_history("cbanner_womens", 7, row["id"])["snapshot"]["content"] for row in rows] == ["正文3", "正文2", "正文1", "正文0"]
    oldest = saved.get_history("cbanner_womens", 7, rows[-1]["id"])["snapshot"]
    assert oldest["input_prompt"] == "输入0"
    token = saved.claim(values, timeout_seconds=180, force_regenerate=True)
    saved.fail("cbanner_womens", 7, token, "模型超时", 504)
    assert saved.list_history("cbanner_womens", 7) == rows
    saved.create_tables()
    assert saved.list_history("cbanner_womens", 7) == rows


@pytest.mark.parametrize("status", ["completed", "failed", "running"])
def test_history_migration_preserves_existing_rows_and_imports_available_snapshots(saved, product, status):
    values = saved_values(product)
    previous = {**values, "content": "旧结果", "generated_at": "2026-09-21 15:04:49+08:00", "input_prompt": None}
    previous = json.loads(json.dumps(previous, default=str))
    with saved.engine.begin() as connection:
        connection.execute(PRODUCT_COPYWRITING_TABLE.insert().values(
            **values, status=status, previous_result=previous,
            content="当前结果" if status == "completed" else None,
            generated_at=datetime(2026, 9, 22, tzinfo=timezone.utc) if status == "completed" else None,
        ))
    PRODUCT_COPYWRITING_HISTORY_TABLE.drop(saved.engine)
    before = saved.get("cbanner_womens", 7)
    saved.create_tables()
    saved.create_tables()
    assert saved.get("cbanner_womens", 7) == before
    rows = saved.list_history("cbanner_womens", 7)
    assert len(rows) == (2 if status == "completed" else 1)
    oldest = saved.get_history("cbanner_womens", 7, rows[-1]["id"])["snapshot"]
    assert oldest["content"] == "旧结果"
    assert oldest["input_prompt"] is None
    assert oldest["generated_at"] == "2026-09-21T07:04:49+00:00"


def test_history_insert_failure_rolls_back_completion(saved, product, monkeypatch):
    token = saved.claim(saved_values(product), timeout_seconds=180)
    before = saved.get("cbanner_womens", 7)
    monkeypatch.setattr(saved, "_save_snapshot", Mock(side_effect=RuntimeError("history unavailable")))
    with pytest.raises(RuntimeError):
        saved.complete("cbanner_womens", 7, token, "不能部分保存")
    assert saved.get("cbanner_womens", 7) == before
    assert saved.list_history("cbanner_womens", 7) == []


def test_history_same_text_on_distinct_generations_is_not_deduplicated(saved, product):
    for _ in range(2):
        token = saved.claim(saved_values(product), timeout_seconds=180, force_regenerate=True)
        saved.complete("cbanner_womens", 7, token, "相同正文")
    assert len(saved.list_history("cbanner_womens", 7)) == 2


def test_late_imported_history_is_sorted_by_generation_time_not_insert_id(saved, product):
    values = saved_values(product)
    token = saved.claim(values, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "较新的结果")
    newest_id = saved.list_history("cbanner_womens", 7)[0]["id"]
    with saved.engine.begin() as connection:
        saved._save_snapshot(connection, "cbanner_womens", 7, {**values, "content": "晚补录的旧版", "generated_at": "2020-01-01T00:00:00Z"})
    rows = saved.list_history("cbanner_womens", 7, limit=1)
    assert rows[0]["id"] == newest_id
    page = saved.list_history("cbanner_womens", 7, before_id=newest_id)
    assert len(page) == 1
    assert page[0]["id"] > newest_id
    assert saved.list_history("eblan", 7, before_id=newest_id) == []


def test_history_api_is_read_only_scoped_and_excludes_sensitive_metadata(client, saved, product, monkeypatch):
    values = {**saved_values(product), "system_prompt": "private-system", "endpoint": "private-endpoint", "input_image": {"archive_path": "private-share", "us3_object_key": "private-key", "source": "us3", "sha256": "private-hash"}}
    token = saved.claim(values, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "历史正文")
    before = saved.get("cbanner_womens", 7)
    monkeypatch.setattr(saved, "_save_snapshot", Mock(side_effect=AssertionError("no writes on GET")))
    monkeypatch.setattr(jobs, "request_doubao_copywriting", Mock(side_effect=AssertionError("no model on GET")))
    monkeypatch.setattr(jobs, "load_product_copywriting_image", Mock(side_effect=AssertionError("no image on GET")))
    client.app.state.settings = None
    listing = client.http.get("/product-copywriting/cbanner_womens/7/history")
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    assert "content" not in listing.text
    version_id = listing.json()["items"][0]["id"]
    detail = client.http.get(f"/product-copywriting/cbanner_womens/7/history/{version_id}")
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "no-store"
    assert detail.json()["content"] == "历史正文"
    assert detail.json()["input_prompt"] == values["input_prompt"]
    assert detail.json()["image_source"] == "us3"
    assert detail.json()["current_template"] is True
    assert "private-" not in detail.text
    assert "system_prompt" not in detail.text
    assert client.http.get(f"/product-copywriting/eblan/7/history/{version_id}").status_code == 404
    assert client.http.get(f"/product-copywriting/cbanner_womens/8/history/{version_id}").status_code == 404
    assert client.http.get("/product-copywriting/eblan/7/history").json()["items"] == []
    assert saved.get("cbanner_womens", 7) == before


def test_history_api_paginates_without_duplicate_or_missing_versions(client, saved, product):
    for index in range(23):
        token = saved.claim(saved_values(product), timeout_seconds=180, force_regenerate=True)
        saved.complete("cbanner_womens", 7, token, str(index))
    first = client.http.get("/product-copywriting/cbanner_womens/7/history").json()
    assert len(first["items"]) == 20
    second = client.http.get(f'/product-copywriting/cbanner_womens/7/history?before_id={first["next_before_id"]}').json()
    assert len(second["items"]) == 3
    assert second["next_before_id"] is None
    assert len({row["id"] for row in first["items"] + second["items"]}) == 23
    assert client.http.get("/product-copywriting/cbanner_womens/7/history?before_id=0").status_code == 422


@pytest.mark.parametrize("suffix", ["history", "history/1"])
@pytest.mark.parametrize("denied", ["department", "permission", "missing_product", "invalid_brand", "login"])
def test_history_requires_same_authorization_as_current_content(client, suffix, denied):
    expected = 403
    if denied == "department":
        client.user["department_code"] = "财务部"
    elif denied == "permission":
        client.user["permissions"] = []
    elif denied == "missing_product":
        client.app.state.repository.get_product.return_value = None
        expected = 404
    elif denied == "invalid_brand":
        client.app.state.repository.is_product_archive_brand.return_value = False
        expected = 400
    else:
        client.app.state.auth_repository.get_user_by_session.return_value = None
        expected = 401
    assert client.http.get(f"/product-copywriting/cbanner_womens/7/{suffix}").status_code == expected


def test_legacy_history_does_not_infer_prompt_or_image_source(client, saved, product):
    values = {**saved_values(product), "input_prompt": None, "template_version": "old", "input_image": {"path": "private-share", "sha256": "old-hash"}}
    token = saved.claim(values, timeout_seconds=180)
    saved.complete("cbanner_womens", 7, token, "旧正文")
    history_id = saved.list_history("cbanner_womens", 7)[0]["id"]
    result = client.http.get(f"/product-copywriting/cbanner_womens/7/history/{history_id}").json()
    assert result["input_prompt"] is None
    assert result["image_source"] == "unknown"
    assert result["current_template"] is False
