from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, inspect, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from domain.product_copywriting_schema import PRODUCT_COPYWRITING_HISTORY_TABLE, PRODUCT_COPYWRITING_TABLE


SNAPSHOT_FIELDS = (
    "content", "input_prompt", "system_prompt", "input_image", "source_facts", "source_hash",
    "source_updated_at", "sku", "launch_date", "generated_at", "provider", "model", "endpoint", "template_version",
)


class ProductCopywritingRepository:
    def __init__(self, engine):
        self.engine = engine

    def create_tables(self) -> None:
        PRODUCT_COPYWRITING_TABLE.create(self.engine, checkfirst=True)
        with self.engine.begin() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns(PRODUCT_COPYWRITING_TABLE.name)}
            for name, sql_type in (("input_prompt", "TEXT"), ("system_prompt", "TEXT"), ("input_image", "JSON"), ("previous_result", "JSON")):
                if name not in columns:
                    optional = "IF NOT EXISTS " if self.engine.dialect.name == "postgresql" else ""
                    connection.execute(text(f"ALTER TABLE product_copywriting ADD COLUMN {optional}{name} {sql_type}"))
        PRODUCT_COPYWRITING_HISTORY_TABLE.create(self.engine, checkfirst=True)
        with self.engine.begin() as connection:
            rows = connection.execute(select(PRODUCT_COPYWRITING_TABLE)).mappings()
            for row in rows:
                self._archive_existing(connection, row)

    def _save_snapshot(self, connection, brand: str, product_id: int, value: dict | None) -> None:
        if not isinstance(value, dict) or not isinstance(value.get("content"), str) or not value["content"].strip():
            return
        try:
            generated_at = datetime.fromisoformat(str(value.get("generated_at") or ""))
        except ValueError:
            return
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        generated_at = generated_at.astimezone(timezone.utc)
        snapshot = json.loads(json.dumps({key: value.get(key) for key in SNAPSHOT_FIELDS}, ensure_ascii=False, default=str))
        snapshot["generated_at"] = generated_at.isoformat()
        snapshot_key = hashlib.sha256(json.dumps(
            [snapshot["generated_at"], snapshot["content"]], ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        insert = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        connection.execute(insert(PRODUCT_COPYWRITING_HISTORY_TABLE).values(
            brand=brand, source_product_id=product_id, snapshot_key=snapshot_key,
            generated_at=generated_at, model=value.get("model") or "", sku=value.get("sku") or "", snapshot=snapshot,
        ).on_conflict_do_nothing(index_elements=["brand", "source_product_id", "snapshot_key"]))

    def _archive_existing(self, connection, row) -> None:
        self._save_snapshot(connection, row["brand"], row["source_product_id"], row.get("previous_result"))
        if row["status"] == "completed":
            self._save_snapshot(connection, row["brand"], row["source_product_id"], dict(row))

    def list_history(self, brand: str, product_id: int, *, before_id: int | None = None, limit: int = 20) -> list[dict]:
        table = PRODUCT_COPYWRITING_HISTORY_TABLE
        statement = select(table.c.id, table.c.generated_at, table.c.model, table.c.sku).where(
            table.c.brand == brand, table.c.source_product_id == product_id,
        )
        with self.engine.connect() as connection:
            if before_id is not None:
                cursor = connection.execute(select(table.c.generated_at).where(
                    table.c.id == before_id, table.c.brand == brand, table.c.source_product_id == product_id,
                )).scalar_one_or_none()
                if cursor is None:
                    return []
                statement = statement.where(or_(
                    table.c.generated_at < cursor,
                    and_(table.c.generated_at == cursor, table.c.id < before_id),
                ))
            return [dict(row) for row in connection.execute(statement.order_by(table.c.generated_at.desc(), table.c.id.desc()).limit(limit)).mappings()]

    def get_history(self, brand: str, product_id: int, history_id: int) -> dict | None:
        table = PRODUCT_COPYWRITING_HISTORY_TABLE
        with self.engine.connect() as connection:
            row = connection.execute(select(table).where(
                table.c.brand == brand, table.c.source_product_id == product_id, table.c.id == history_id,
            )).mappings().first()
        return dict(row) if row else None

    def get(self, brand: str, product_id: int) -> dict | None:
        table = PRODUCT_COPYWRITING_TABLE
        with self.engine.connect() as connection:
            row = connection.execute(select(table).where(
                table.c.brand == brand, table.c.source_product_id == product_id,
            )).mappings().first()
        return dict(row) if row else None

    def claim(
        self,
        values: dict,
        *,
        timeout_seconds: int,
        retry_failed: bool = False,
        refresh_outdated_template: bool = False,
        force_regenerate: bool = False,
        only_if_missing: bool = False,
    ) -> str | None:
        table = PRODUCT_COPYWRITING_TABLE
        now = datetime.now(timezone.utc)
        token = uuid.uuid4().hex
        insert = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        if only_if_missing:
            if retry_failed or refresh_outdated_template or force_regenerate:
                raise ValueError("only_if_missing cannot be combined with regeneration options")
            with self.engine.begin() as connection:
                statement = insert(table).values(
                    **values, status="running", claim_token=token,
                    lease_expires_at=now + timedelta(seconds=timeout_seconds + 120),
                    attempt_count=1, updated_at=now,
                ).on_conflict_do_nothing(
                    index_elements=["brand", "source_product_id"],
                ).returning(table.c.claim_token)
                return connection.execute(statement).scalar_one_or_none()
        conditions = [table.c.status == "pending"]
        if retry_failed:
            conditions.extend([
                table.c.status == "failed",
                and_(table.c.status == "running", table.c.lease_expires_at < now),
            ])
        if refresh_outdated_template:
            conditions.append(and_(
                table.c.template_version != values["template_version"],
                or_(
                    table.c.status.in_(("completed", "failed")),
                    and_(table.c.status == "running", table.c.lease_expires_at < now),
                ),
            ))
        if force_regenerate:
            conditions.append(or_(
                table.c.status.in_(("completed", "failed")),
                and_(table.c.status == "running", or_(table.c.lease_expires_at < now, table.c.lease_expires_at.is_(None))),
            ))
        with self.engine.begin() as connection:
            connection.execute(insert(table).values(**values).on_conflict_do_nothing(
                index_elements=["brand", "source_product_id"],
            ))
            eligible = and_(
                table.c.brand == values["brand"],
                table.c.source_product_id == values["source_product_id"],
                or_(*conditions),
            )
            previous = connection.execute(select(table).where(eligible).with_for_update()).mappings().first()
            if previous is None:
                return None
            self._archive_existing(connection, previous)
            previous_result = previous["previous_result"]
            if previous["status"] == "completed":
                previous_result = json.loads(json.dumps({
                    key: previous[key] for key in SNAPSHOT_FIELDS
                }, ensure_ascii=False, default=str))
            result = connection.execute(update(table).where(eligible).values(
                **values,
                status="running",
                content=None,
                generated_at=None,
                previous_result=previous_result,
                claim_token=token,
                lease_expires_at=now + timedelta(seconds=timeout_seconds + 120),
                attempt_count=table.c.attempt_count + 1,
                last_error=None,
                error_status=None,
                updated_at=now,
            ))
            return token if result.rowcount == 1 else None

    def record_input_image(self, brand: str, product_id: int, token: str, image: dict) -> bool:
        table = PRODUCT_COPYWRITING_TABLE
        with self.engine.begin() as connection:
            result = connection.execute(update(table).where(
                table.c.brand == brand, table.c.source_product_id == product_id,
                table.c.status == "running", table.c.claim_token == token,
                table.c.lease_expires_at > datetime.now(timezone.utc),
            ).values(input_image=image, updated_at=datetime.now(timezone.utc)))
            return result.rowcount == 1

    def complete(self, brand: str, product_id: int, token: str, content: str) -> bool:
        table = PRODUCT_COPYWRITING_TABLE
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            row = connection.execute(update(table).where(
                table.c.brand == brand, table.c.source_product_id == product_id,
                table.c.status == "running", table.c.claim_token == token,
            ).values(
                status="completed", content=content, generated_at=now, updated_at=now,
                lease_expires_at=None, claim_token=None, last_error=None, error_status=None,
            ).returning(table)).mappings().first()
            if row is None:
                return False
            self._save_snapshot(connection, brand, product_id, dict(row))
            return True

    def fail(self, brand: str, product_id: int, token: str, message: str, status: int) -> bool:
        table = PRODUCT_COPYWRITING_TABLE
        with self.engine.begin() as connection:
            result = connection.execute(update(table).where(
                table.c.brand == brand, table.c.source_product_id == product_id,
                table.c.status == "running", table.c.claim_token == token,
            ).values(
                status="failed", last_error=message, error_status=status,
                claim_token=None, lease_expires_at=None, updated_at=datetime.now(timezone.utc),
            ))
        return result.rowcount == 1
