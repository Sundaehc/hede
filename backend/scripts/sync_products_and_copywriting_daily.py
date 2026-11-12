"""Maintain images, copywriting and tags for web-managed product archives."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

from sqlalchemy import text

from config import BACKEND_ROOT, load_settings
from scripts.sync_product_tags_daily import TASK_NAME as TAG_TASK_NAME, run_daily_sync as run_daily_tag_sync
from scripts.generate_product_copywriting_daily import TASK_NAME as COPYWRITING_TASK_NAME, business_today, run_daily_generation
from scripts.refresh_product_images import TASK_NAME as IMAGE_TASK_NAME
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "sync_products_and_copywriting_daily"
WORKFLOW_LOCK_ID = 68473102
IMAGE_MODULE = "refresh_product_images"


def run_import(module: str, task_name: str, log_file: str) -> int:
    if module != IMAGE_MODULE:
        raise ValueError("每日商品维护只运行图片步骤，不再导入外部商品档案或物价")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    command = [
        sys.executable, "-m", "scripts.run_scheduled_task", "--task-name", task_name,
        "--log-file", f"logs/{log_file}", "--skip-if-business-success", IMAGE_TASK_NAME,
        "--", sys.executable, "-m", f"scripts.{module}",
    ]
    command.append("--daily")
    return subprocess.run(command, cwd=BACKEND_ROOT, env=environment, check=False).returncode


def run_workflow(settings, statuses, business_date: date) -> int:
    if statuses.is_success(TASK_NAME, business_date):
        print(f"[SKIP] {business_date.isoformat()} web product maintenance already succeeded")
        return 0
    statuses.mark_running(TASK_NAME, business_date)
    try:
        if business_today() != business_date:
            statuses.mark_finished(TASK_NAME, business_date, status="failed", message="任务跨日，已停止生成，请按新业务日期重试")
            return 1
        if not statuses.is_success(IMAGE_TASK_NAME, business_date):
            exit_code = run_import(IMAGE_MODULE, "HedeRefreshProductImages", "refresh_product_images.log")
            if exit_code != 0 or not statuses.is_success(IMAGE_TASK_NAME, business_date):
                statuses.mark_finished(
                    TASK_NAME,
                    business_date,
                    status="failed",
                    message="商品图片同步未成功，不执行提示词生成",
                )
                print("[WAIT] product image refresh did not succeed; copywriting generation was not started")
                return 1
        if business_today() != business_date:
            statuses.mark_finished(TASK_NAME, business_date, status="failed", message="图片同步跨日，已停止生成，请按新业务日期重试")
            return 1
        if not statuses.is_success(COPYWRITING_TASK_NAME, business_date):
            statuses.mark_running(COPYWRITING_TASK_NAME, business_date)
            try:
                result = run_daily_generation(settings, business_date)
            except Exception:
                statuses.mark_finished(COPYWRITING_TASK_NAME, business_date, status="failed", message="自动提示词生成未完成，请检查配置和日志")
                raise
            failed = bool(result.get("failed"))
            status = "failed" if failed else "success"
            message = f"近5天商品提示词：新增成功{result.get('completed', 0)}，跳过{result.get('skipped', 0)}，失败{result.get('failed', 0)}；已有记录不变"
            statuses.mark_finished(COPYWRITING_TASK_NAME, business_date, status=status, message=message, result=result)
            if failed:
                statuses.mark_finished(TASK_NAME, business_date, status="failed", message=message, result=result)
                print(f"[FAILED] {business_date.isoformat()} {message}")
                return 1
        if business_today() != business_date:
            statuses.mark_finished(TASK_NAME, business_date, status="failed", message="提示词生成跨日，已停止标签同步，请按新业务日期重试")
            return 1
        if not statuses.is_success(TAG_TASK_NAME, business_date):
            statuses.mark_running(TAG_TASK_NAME, business_date)
            try:
                tag_result = run_daily_tag_sync(settings, business_date)
            except Exception:
                statuses.mark_finished(TAG_TASK_NAME, business_date, status="failed", message="商品标签同步失败，请检查任务日志")
                statuses.mark_finished(TASK_NAME, business_date, status="failed", message="商品标签同步失败，等待下次计划重试")
                return 1
            statuses.mark_finished(
                TAG_TASK_NAME, business_date, status="success",
                message=f"商品标签同步完成：处理{tag_result['products']}个商品，新增{tag_result['tag_definitions']}个标签",
                result=tag_result,
            )
        statuses.mark_finished(TASK_NAME, business_date, status="success", message="基于网页商品档案的图片、提示词及标签维护完成")
        print(f"[OK] {business_date.isoformat()} web product images, copywriting and tags completed")
        return 0
    except Exception:
        statuses.mark_finished(TASK_NAME, business_date, status="failed", message="商品图片、提示词与标签维护异常，请检查分步任务日志")
        print(f"[FAILED] {business_date.isoformat()} workflow interrupted; existing copywriting preserved")
        return 1


def main() -> int:
    settings = load_settings(require_database=True)
    statuses = ScheduledTaskStatusRepository(settings.database_url)
    try:
        with statuses.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            acquired = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKFLOW_LOCK_ID}).scalar_one()
            if not acquired:
                print("[SKIP] product archive and copywriting workflow is already running")
                return 0
            try:
                return run_workflow(settings, statuses, business_today())
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKFLOW_LOCK_ID})
    finally:
        statuses.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
