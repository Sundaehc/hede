from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select

from domain.task_status_schema import SCHEDULED_TASK_RUN_TABLE, SCHEDULED_TASK_STATUS_TABLE


router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])

SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
RUN_STATUSES = {"running", "success", "failed"}
BUSINESS_STATUSES = {"running", "success", "failed", "skipped"}


def _require_scheduled_task_access(request: Request) -> None:
    user = getattr(request.state, "current_user", None) or {}
    role_code = str(user.get("role_code") or "").strip()
    department_code = str(user.get("department_code") or "").strip()
    if role_code != "super_admin" and department_code != "开发部":
        raise HTTPException(status_code=403, detail="定时任务执行情况仅限开发部和超级管理员查看")


def _engine(request: Request):
    return request.app.state.inventory_repository.engine


def _date_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=SHANGHAI_TIMEZONE)
    return start, start + timedelta(days=1)


def _normalize_status(value: str | None, allowed: set[str]) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized or normalized == "all":
        return None
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail="无效的任务状态")
    return normalized


def _run_conditions(run_date: date, status: str | None, query: str | None):
    table = SCHEDULED_TASK_RUN_TABLE
    start, end = _date_bounds(run_date)
    conditions = [table.c.started_at >= start, table.c.started_at < end]
    if status:
        conditions.append(table.c.status == status)
    normalized_query = str(query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        conditions.append(
            or_(
                table.c.task_name.ilike(pattern),
                table.c.command.ilike(pattern),
                table.c.log_path.ilike(pattern),
                table.c.error_summary.ilike(pattern),
            )
        )
    return and_(*conditions)


def _serialize_mapping(row) -> dict[str, object]:
    return dict(row)


@router.get("/runs")
def list_scheduled_task_runs(
    request: Request,
    run_date: date = Query(default_factory=lambda: datetime.now(SHANGHAI_TIMEZONE).date()),
    status: str | None = None,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    _require_scheduled_task_access(request)
    normalized_status = _normalize_status(status, RUN_STATUSES)
    table = SCHEDULED_TASK_RUN_TABLE
    criterion = _run_conditions(run_date, normalized_status, query)
    unfiltered_criterion = _run_conditions(run_date, None, query)

    summary_statement = (
        select(
            func.count().label("total"),
            func.count().filter(table.c.status == "success").label("success"),
            func.count().filter(table.c.status == "failed").label("failed"),
            func.count().filter(table.c.status == "running").label("running"),
            func.count(func.distinct(table.c.task_name)).label("task_count"),
            func.max(table.c.started_at).label("latest_started_at"),
        )
        .select_from(table)
        .where(unfiltered_criterion)
    )
    count_statement = select(func.count()).select_from(table).where(criterion)
    items_statement = (
        select(table)
        .where(criterion)
        .order_by(table.c.started_at.desc(), table.c.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    with _engine(request).connect() as connection:
        summary = connection.execute(summary_statement).mappings().one()
        total = int(connection.execute(count_statement).scalar_one())
        items = [
            _serialize_mapping(row)
            for row in connection.execute(items_statement).mappings().all()
        ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "run_date": run_date,
        "summary": {
            "total": int(summary["total"] or 0),
            "success": int(summary["success"] or 0),
            "failed": int(summary["failed"] or 0),
            "running": int(summary["running"] or 0),
            "task_count": int(summary["task_count"] or 0),
            "latest_started_at": summary["latest_started_at"],
        },
    }


@router.get("/history")
def list_scheduled_task_history(
    request: Request,
    task_name: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    _require_scheduled_task_access(request)
    normalized_task_name = task_name.strip()
    if not normalized_task_name:
        raise HTTPException(status_code=400, detail="任务名称不能为空")

    table = SCHEDULED_TASK_RUN_TABLE
    statement = (
        select(table)
        .where(table.c.task_name == normalized_task_name)
        .order_by(table.c.started_at.desc(), table.c.id.desc())
        .limit(limit)
    )
    with _engine(request).connect() as connection:
        items = [
            _serialize_mapping(row)
            for row in connection.execute(statement).mappings().all()
        ]
    return {"items": items, "task_name": normalized_task_name}


@router.get("/business-statuses")
def list_scheduled_task_business_statuses(
    request: Request,
    business_date: date = Query(default_factory=lambda: datetime.now(SHANGHAI_TIMEZONE).date()),
    status: str | None = None,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    _require_scheduled_task_access(request)
    normalized_status = _normalize_status(status, BUSINESS_STATUSES)
    normalized_query = str(query or "").strip()
    table = SCHEDULED_TASK_STATUS_TABLE
    base_conditions = [table.c.business_date == business_date]
    if normalized_query:
        pattern = f"%{normalized_query}%"
        base_conditions.append(
            or_(
                table.c.task_name.ilike(pattern),
                table.c.source_path.ilike(pattern),
                table.c.message.ilike(pattern),
            )
        )
    conditions = list(base_conditions)
    if normalized_status:
        conditions.append(table.c.status == normalized_status)
    criterion = and_(*conditions)
    summary_statement = (
        select(
            func.count().label("total"),
            func.count().filter(table.c.status == "success").label("success"),
            func.count().filter(table.c.status == "failed").label("failed"),
            func.count().filter(table.c.status == "running").label("running"),
            func.count().filter(table.c.status == "skipped").label("skipped"),
        )
        .select_from(table)
        .where(and_(*base_conditions))
    )
    count_statement = select(func.count()).select_from(table).where(criterion)
    items_statement = (
        select(table)
        .where(criterion)
        .order_by(table.c.last_started_at.desc().nullslast(), table.c.task_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    with _engine(request).connect() as connection:
        summary = connection.execute(summary_statement).mappings().one()
        total = int(connection.execute(count_statement).scalar_one())
        items = [
            _serialize_mapping(row)
            for row in connection.execute(items_statement).mappings().all()
        ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "business_date": business_date,
        "summary": {
            "total": int(summary["total"] or 0),
            "success": int(summary["success"] or 0),
            "failed": int(summary["failed"] or 0),
            "running": int(summary["running"] or 0),
            "skipped": int(summary["skipped"] or 0),
        },
    }
