from datetime import datetime, timezone
import hashlib

from sqlalchemy import create_engine, text
from readonly_mcp.catalog import DEPARTMENT_PROFILES, PROFILE_PERMISSIONS


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ControlRepository:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_size=4, max_overflow=0, pool_timeout=2, pool_pre_ping=True, hide_parameters=True, connect_args={"connect_timeout": 5, "options": "-c statement_timeout=3000 -c lock_timeout=1000"})

    def authenticate(self, token: str) -> dict | None:
        if not token.startswith("hmcp_") or len(token) > 150:
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.engine.connect() as connection:
            row = connection.execute(text("""SELECT token_id, user_id, profile, expires_at, revoked_at,
                status, department_code, role_code, permissions
                FROM mcp_private.identities WHERE token_hash=:token_hash"""), {"token_hash": token_hash}).mappings().first()
        if row is None or row["revoked_at"] or row["status"] != "active":
            return None
        if row["expires_at"] is not None and utc(row["expires_at"]) <= datetime.now(timezone.utc):
            return None
        permissions = {value.strip() for value in (row["permissions"] or "").split(",")}
        if "*" not in permissions and "product.view" not in permissions:
            return None
        if row["profile"] == "design" and row["role_code"] != "super_admin" and row["department_code"] != "美工部":
            return None
        if row["profile"] in PROFILE_PERMISSIONS:
            if row["role_code"] != "super_admin" and DEPARTMENT_PROFILES.get(row["department_code"]) != row["profile"]:
                return None
            if "*" not in permissions and not permissions.intersection(PROFILE_PERMISSIONS[row["profile"]]):
                return None
        elif row["profile"] != "design":
            return None
        return {"token_id": row["token_id"], "user_id": row["user_id"], "profile": row["profile"], "permissions": row["permissions"]}

    def audit(self, request_id: str, principal: dict, tool: str, sql_hash: str | None, status: str, row_count: int = 0, elapsed_ms: int = 0):
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO mcp_private.audit
                (request_id, token_id, user_id, tool, sql_hash, status, row_count, elapsed_ms)
                VALUES (:request_id, :token_id, :user_id, :tool, :sql_hash, :status, :row_count, :elapsed_ms)"""), {
                "request_id": request_id, "token_id": principal["token_id"], "user_id": principal["user_id"],
                "tool": tool, "sql_hash": sql_hash, "status": status, "row_count": row_count, "elapsed_ms": elapsed_ms,
            })

    def close(self):
        self.engine.dispose()
