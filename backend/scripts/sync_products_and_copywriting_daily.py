from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

from sqlalchemy import text

from config import BACKEND_ROOT, load_settings
from scripts.generate_product_copywriting_daily import TASK_NAME as COPYWRITING_TASK_NAME, business_today, run_daily_generation
from scripts.sync_products_daily import TASK_NAME as PRODUCT_TASK_NAME
from storage.task_status_repository import ScheduledTaskStatusRepository


TASK_NAME = "sync_products_and_copywriting_daily"
WORKFLOW_LOCK_ID = 68473102
PREREQUISITES = (
    ("import_price_daily", "HedeImportPriceDaily", "import_price_daily.log"),
    ("import_gj_merged_product_info_daily", "hede_import_gj_merged_product_info_daily", "import_gj_merged_product_info.log"),
)


def run_import(module: str, task_name: str, log_file: str) -> int:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    command = [
        sys.executable, "-m", "scripts.run_scheduled_task", "--task-name", task_name,
        "--log-file", f"logs/{log_file}", "--skip-if-business-success", module,
        "--", sys.executable, "-m", f"scripts.{module}",
    ]
    if module != PRODUCT_TASK_NAME:
        command.extend(["--lookback-days", "7", "--allow-missing-current"])
    return subprocess.run(command, cwd=BACKEND_ROOT, env=environment, check=False).returncode


def run_workflow(settings, statuses, business_date: date) -> int:
    if statuses.is_success(TASK_NAME, business_date):
        print(f"[SKIP] {business_date.isoformat()} product archive and copywriting workflow already succeeded")
        return 0
    statuses.mark_running(TASK_NAME, business_date)
    try:
        if not statuses.is_success(PRODUCT_TASK_NAME, business_date):
            for module, task_name, log_file in PREREQUISITES:
                if not statuses.is_success(module, business_date):
                    run_import(module, task_name, log_file)
            pending = [module for module, _, _ in PREREQUISITES if not statuses.is_success(module, business_date)]
            if pending:
                statuses.mark_finished(
                    TASK_NAME, business_date, status="skipped", message="前置源数据尚未就绪，等待下次计划重试",
                    result={"pending_prerequisites": pending},
                )
                print(f"[WAIT] {business_date.isoformat()} prerequisites not ready: {', '.join(pending)}")
                return 0
            exit_code = run_import(PRODUCT_TASK_NAME, "HedeSyncProductArchives", "sync_product_archives.log")
            if exit_code != 0 or not statuses.is_success(PRODUCT_TASK_NAME, business_date):
                statuses.mark_finished(TASK_NAME, business_date, status="failed", message="商品档案同步未成功，不执行提示词生成")
                return 1
        if business_today() != business_date:
            statuses.mark_finished(TASK_NAME, business_date, status="failed", message="任务跨日，已停止生成，请按新业务日期重试")
            return 1
        statuses.mark_running(COPYWRITING_TASK_NAME, business_date)
        try:
            result = run_daily_generation(settings, business_date)
        except Exception:
            statuses.mark_finished(COPYWRITING_TASK_NAME, business_date, status="failed", message="自动提示词生成未完成，请检查配置和日志")
            raise
        failed = bool(result.get("failed"))
        status = "failed" if failed else "success"
        message = f"近7天商品提示词：新增成功{result.get('completed', 0)}，跳过{result.get('skipped', 0)}，失败{result.get('failed', 0)}；已有记录不变"
        statuses.mark_finished(COPYWRITING_TASK_NAME, business_date, status=status, message=message, result=result)
        statuses.mark_finished(TASK_NAME, business_date, status=status, message=message, result=result)
        print(f"[{'FAILED' if failed else 'OK'}] {business_date.isoformat()} {message}")
        return 1 if failed else 0
    except Exception:
        statuses.mark_finished(TASK_NAME, business_date, status="failed", message="商品档案与提示词串行任务异常，请检查分步任务日志")
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
