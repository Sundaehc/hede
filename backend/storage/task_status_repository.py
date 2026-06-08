from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import orjson
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.task_status_schema import SCHEDULED_TASK_STATUS_TABLE


def _json_serializer(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


class ScheduledTaskStatusRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True, json_serializer=_json_serializer)

    def ensure_table(self) -> None:
        SCHEDULED_TASK_STATUS_TABLE.create(self.engine, checkfirst=True)

    def successful_dates(self, task_name: str, start_date: date, end_date: date) -> set[date]:
        self.ensure_table()
        statement = (
            select(SCHEDULED_TASK_STATUS_TABLE.c.business_date)
            .where(SCHEDULED_TASK_STATUS_TABLE.c.task_name == task_name)
            .where(SCHEDULED_TASK_STATUS_TABLE.c.status == "success")
            .where(SCHEDULED_TASK_STATUS_TABLE.c.business_date >= start_date)
            .where(SCHEDULED_TASK_STATUS_TABLE.c.business_date <= end_date)
        )
        with self.engine.connect() as connection:
            return {
                row[0]
                for row in connection.execute(statement)
                if isinstance(row[0], date)
            }

    def is_success(self, task_name: str, business_date: date) -> bool:
        self.ensure_table()
        statement = (
            select(SCHEDULED_TASK_STATUS_TABLE.c.status)
            .where(SCHEDULED_TASK_STATUS_TABLE.c.task_name == task_name)
            .where(SCHEDULED_TASK_STATUS_TABLE.c.business_date == business_date)
        )
        with self.engine.connect() as connection:
            return connection.execute(statement).scalar_one_or_none() == "success"

    def mark_running(self, task_name: str, business_date: date, *, source_path: Path | str | None = None) -> None:
        self.ensure_table()
        table = SCHEDULED_TASK_STATUS_TABLE
        values = {
            "task_name": task_name,
            "business_date": business_date,
            "status": "running",
            "source_path": str(source_path) if source_path is not None else None,
            "message": None,
            "result": None,
            "attempts": 1,
            "first_started_at": func.now(),
            "last_started_at": func.now(),
            "finished_at": None,
        }
        statement = pg_insert(table).values(**values).on_conflict_do_update(
            index_elements=["task_name", "business_date"],
            set_={
                "status": "running",
                "source_path": values["source_path"],
                "message": None,
                "result": None,
                "attempts": table.c.attempts + 1,
                "first_started_at": func.coalesce(table.c.first_started_at, func.now()),
                "last_started_at": func.now(),
                "finished_at": None,
                "updated_at": func.date_trunc("minute", func.now()),
            },
        )
        with self.engine.begin() as connection:
            connection.execute(statement)

    def mark_finished(
        self,
        task_name: str,
        business_date: date,
        *,
        status: str,
        message: str,
        result: Mapping[str, Any] | None = None,
        source_path: Path | str | None = None,
    ) -> None:
        if status not in {"success", "skipped", "failed"}:
            raise ValueError(f"Unsupported task status: {status}")

        self.ensure_table()
        table = SCHEDULED_TASK_STATUS_TABLE
        values = {
            "task_name": task_name,
            "business_date": business_date,
            "status": status,
            "source_path": str(source_path) if source_path is not None else None,
            "message": message,
            "result": _json_safe(result) if result is not None else None,
            "attempts": 1,
            "first_started_at": func.now(),
            "last_started_at": func.now(),
            "finished_at": func.now(),
        }
        statement = pg_insert(table).values(**values).on_conflict_do_update(
            index_elements=["task_name", "business_date"],
            set_={
                "status": status,
                "source_path": values["source_path"],
                "message": message,
                "result": values["result"],
                "finished_at": func.now(),
                "updated_at": func.date_trunc("minute", func.now()),
            },
        )
        with self.engine.begin() as connection:
            connection.execute(statement)
