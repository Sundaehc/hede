from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

import orjson
from sqlalchemy import and_, create_engine, desc, func, insert, select

from domain.operation_log_schema import OPERATION_LOG_TABLE


def _json_serializer(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")


def _clean_value(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return str(normalized) if normalized.as_tuple().exponent < 0 else str(int(normalized))
    if isinstance(value, Mapping):
        return {str(key): _clean_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_value(item) for item in value]
    return value


def clean_payload(value: object) -> object:
    return _clean_value(value)


class OperationLogRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(
            database_url,
            future=True,
            json_serializer=_json_serializer,
        )

    def create_tables(self) -> None:
        OPERATION_LOG_TABLE.create(self.engine, checkfirst=True)

    def create_log(
        self,
        *,
        module: str,
        action: str,
        entity_type: str,
        entity_id: object | None = None,
        entity_label: str | None = None,
        summary: str,
        changed_fields: object | None = None,
        before_data: object | None = None,
        after_data: object | None = None,
        user: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        actor = user or {}
        payload = {
            "module": module,
            "action": action,
            "entity_type": entity_type,
            "entity_id": None if entity_id is None else str(entity_id),
            "entity_label": entity_label,
            "summary": summary,
            "changed_fields": clean_payload(changed_fields),
            "before_data": clean_payload(before_data),
            "after_data": clean_payload(after_data),
            "user_id": actor.get("id"),
            "username": actor.get("username"),
            "display_name": actor.get("display_name"),
            "department_name": actor.get("department_name"),
        }
        with self.engine.begin() as connection:
            row = connection.execute(insert(OPERATION_LOG_TABLE).values(**payload).returning(OPERATION_LOG_TABLE)).mappings().one()
        return dict(row)

    def list_logs(
        self,
        *,
        module: str | None,
        query: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        table = OPERATION_LOG_TABLE
        conditions = []
        if module:
            conditions.append(table.c.module == module)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(
                table.c.summary.ilike(pattern)
                | table.c.entity_label.ilike(pattern)
                | table.c.username.ilike(pattern)
                | table.c.display_name.ilike(pattern)
            )

        criterion = and_(*conditions) if conditions else None
        count_statement = select(func.count()).select_from(table)
        items_statement = select(table).order_by(desc(table.c.created_at), desc(table.c.id)).offset((page - 1) * page_size).limit(page_size)
        if criterion is not None:
            count_statement = count_statement.where(criterion)
            items_statement = items_statement.where(criterion)

        with self.engine.connect() as connection:
            total = connection.execute(count_statement).scalar_one()
            items = [dict(row) for row in connection.execute(items_statement).mappings()]
        return {
            "items": [clean_payload(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
