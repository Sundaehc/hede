from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select, update

from domain.auth_schema import PRODUCT_IMAGE_TOKEN_TABLE as tokens


TOKEN_PREFIX = "himg_"
METADATA_COLUMNS = (tokens.c.id, tokens.c.label, tokens.c.created_at, tokens.c.expires_at, tokens.c.revoked_at)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_token(connection, *, label: str, days: int) -> tuple[dict, str]:
    label = label.strip()
    if not 1 <= len(label) <= 100 or not 1 <= days <= 90:
        raise ValueError("Label must be 1–100 characters and lifetime 1–90 days")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    statement = insert(tokens).values(label=label, token_hash=_digest(token), expires_at=expires_at)
    item = connection.execute(statement.returning(*METADATA_COLUMNS)).mappings().one()
    return dict(item), token


def list_tokens(connection) -> list[dict]:
    return [dict(row) for row in connection.execute(select(*METADATA_COLUMNS).order_by(tokens.c.id)).mappings()]


def revoke_token(connection, token_id: int) -> dict | None:
    statement = (
        update(tokens)
        .where(tokens.c.id == token_id, tokens.c.revoked_at.is_(None))
        .values(revoked_at=func.now())
        .returning(*METADATA_COLUMNS)
    )
    row = connection.execute(statement).mappings().one_or_none()
    if row is None:
        row = connection.execute(select(*METADATA_COLUMNS).where(tokens.c.id == token_id)).mappings().one_or_none()
    return dict(row) if row is not None else None


def is_active_token(engine, token: str) -> bool:
    statement = select(tokens.c.id).where(
        tokens.c.token_hash == _digest(token),
        tokens.c.revoked_at.is_(None),
        tokens.c.expires_at > func.now(),
    )
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one_or_none() is not None
