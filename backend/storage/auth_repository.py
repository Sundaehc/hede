from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, create_engine, delete, func, insert, select, text, update

from domain.auth_schema import AUTH_DEPARTMENT_TABLE, AUTH_ROLE_TABLE, AUTH_SESSION_TABLE, AUTH_USER_TABLE, METADATA


SESSION_COOKIE_NAME = "hede_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

DEPARTMENTS = [
    {"code": "财务部", "name": "财务部"},
    {"code": "商品部", "name": "商品部"},
    {"code": "运营部", "name": "运营部"},
    {"code": "开发部", "name": "开发部"},
    {"code": "美工部", "name": "美工部"},
]

LEGACY_DEPARTMENT_CODE_MAP = {
    "finance": "财务部",
    "product": "商品部",
    "operation": "运营部",
    "design": "美工部",
    "财务组": "财务部",
    "商品组": "商品部",
    "运营组": "运营部",
}

DEFAULT_ROLE_BY_DEPARTMENT = {
    "财务部": "finance_user",
    "商品部": "product_user",
    "运营部": "operation_user",
    "开发部": "developer_user",
    "美工部": "design_viewer",
}

DEFAULT_ROLES = [
    {
        "code": "super_admin",
        "name": "超级管理员",
        "department_code": None,
        "description": "系统全部权限",
        "permissions": "*",
    },
    {
        "code": "finance_user",
        "name": "财务组",
        "department_code": "财务部",
        "description": "查看经营历程和采购相关数据，允许导出",
        "permissions": "inventory.view,inventory.export,purchase.view,purchase.export",
    },
    {
        "code": "product_user",
        "name": "商品组",
        "department_code": "商品部",
        "description": "维护商品档案和采购单，允许精细表导出",
        "permissions": "product.view,product.manage,product.import,product.export,fine_table.view,fine_table.export,purchase.view,purchase.manage,purchase.import,purchase.export,inventory.view",
    },
    {
        "code": "operation_user",
        "name": "运营组",
        "department_code": "运营部",
        "description": "维护商品档案，查看和导出商品档案、精细表",
        "permissions": "product.view,product.manage,product.import,product.export,fine_table.view,fine_table.export",
    },
    {
        "code": "developer_user",
        "name": "开发部",
        "department_code": "开发部",
        "description": "业务全部权限，不含用户管理",
        "permissions": "product.view,product.manage,product.import,product.export,fine_table.view,fine_table.export,inventory.view,inventory.manage,inventory.export,purchase.view,purchase.manage,purchase.import,purchase.export",
    },
    {
        "code": "design_viewer",
        "name": "美工部只读",
        "department_code": "美工部",
        "description": "只允许查看商品信息档案",
        "permissions": "product.view",
    },
]


def hash_password_md5(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _split_permissions(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if text == "*":
        return ["*"]
    return [item.strip() for item in text.split(",") if item.strip()]


def normalize_department_code(value: object) -> str:
    code = str(value or "").strip()
    return LEGACY_DEPARTMENT_CODE_MAP.get(code, code)


def validate_department_code(value: object) -> str:
    code = normalize_department_code(value)
    if code not in DEFAULT_ROLE_BY_DEPARTMENT:
        raise ValueError(f"unknown department_code: {code}")
    return code


class AuthRepository:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)

    def create_tables(self) -> None:
        METADATA.create_all(self.engine)
        self.seed_defaults()
        self.ensure_constraints()

    def seed_defaults(self) -> None:
        with self.engine.begin() as connection:
            for old_code, new_code in LEGACY_DEPARTMENT_CODE_MAP.items():
                if old_code == new_code:
                    continue
                connection.execute(
                    update(AUTH_USER_TABLE)
                    .where(AUTH_USER_TABLE.c.department_code == old_code)
                    .values(department_code=new_code)
                )
                connection.execute(
                    update(AUTH_ROLE_TABLE)
                    .where(AUTH_ROLE_TABLE.c.department_code == old_code)
                    .values(department_code=new_code)
                )
                old_department = connection.execute(
                    select(AUTH_DEPARTMENT_TABLE.c.id).where(AUTH_DEPARTMENT_TABLE.c.code == old_code)
                ).first()
                new_department = connection.execute(
                    select(AUTH_DEPARTMENT_TABLE.c.id).where(AUTH_DEPARTMENT_TABLE.c.code == new_code)
                ).first()
                if old_department is not None and new_department is None:
                    connection.execute(
                        update(AUTH_DEPARTMENT_TABLE)
                        .where(AUTH_DEPARTMENT_TABLE.c.code == old_code)
                        .values(code=new_code, name=new_code)
                    )
                elif old_department is not None:
                    connection.execute(delete(AUTH_DEPARTMENT_TABLE).where(AUTH_DEPARTMENT_TABLE.c.code == old_code))

            for department in DEPARTMENTS:
                existing = connection.execute(
                    select(AUTH_DEPARTMENT_TABLE.c.id).where(AUTH_DEPARTMENT_TABLE.c.code == department["code"])
                ).first()
                if existing is None:
                    connection.execute(insert(AUTH_DEPARTMENT_TABLE).values(**department))
                else:
                    connection.execute(
                        update(AUTH_DEPARTMENT_TABLE)
                        .where(AUTH_DEPARTMENT_TABLE.c.code == department["code"])
                        .values(name=department["name"])
                    )

            for role in DEFAULT_ROLES:
                existing = connection.execute(
                    select(AUTH_ROLE_TABLE.c.id).where(AUTH_ROLE_TABLE.c.code == role["code"])
                ).first()
                if existing is None:
                    connection.execute(insert(AUTH_ROLE_TABLE).values(**role))
                else:
                    connection.execute(
                        update(AUTH_ROLE_TABLE)
                        .where(AUTH_ROLE_TABLE.c.code == role["code"])
                        .values(
                            name=role["name"],
                            department_code=role["department_code"],
                            description=role["description"],
                            permissions=role["permissions"],
                        )
                    )

    def ensure_constraints(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM auth_sessions AS s
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM auth_users AS u
                        WHERE u.id = s.user_id
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_auth_roles_department_code'
                        ) THEN
                            ALTER TABLE auth_roles
                            ADD CONSTRAINT fk_auth_roles_department_code
                            FOREIGN KEY (department_code)
                            REFERENCES auth_departments (code)
                            ON UPDATE CASCADE;
                        END IF;
                    END $$;
                    """
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_auth_users_department_code'
                        ) THEN
                            ALTER TABLE auth_users
                            ADD CONSTRAINT fk_auth_users_department_code
                            FOREIGN KEY (department_code)
                            REFERENCES auth_departments (code)
                            ON UPDATE CASCADE;
                        END IF;
                    END $$;
                    """
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_auth_users_role_code'
                        ) THEN
                            ALTER TABLE auth_users
                            ADD CONSTRAINT fk_auth_users_role_code
                            FOREIGN KEY (role_code)
                            REFERENCES auth_roles (code)
                            ON UPDATE CASCADE;
                        END IF;
                    END $$;
                    """
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'fk_auth_sessions_user_id'
                        ) THEN
                            ALTER TABLE auth_sessions
                            ADD CONSTRAINT fk_auth_sessions_user_id
                            FOREIGN KEY (user_id)
                            REFERENCES auth_users (id)
                            ON DELETE CASCADE;
                        END IF;
                    END $$;
                    """
                )
            )

    def has_users(self) -> bool:
        with self.engine.connect() as connection:
            return (connection.execute(select(func.count()).select_from(AUTH_USER_TABLE)).scalar_one() or 0) > 0

    def list_departments(self) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(select(AUTH_DEPARTMENT_TABLE).order_by(AUTH_DEPARTMENT_TABLE.c.id)).mappings()]

    def list_roles(self) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(select(AUTH_ROLE_TABLE).order_by(AUTH_ROLE_TABLE.c.id)).mappings()]
        for row in rows:
            row["permissions"] = _split_permissions(row.get("permissions"))
        return rows

    def create_user(self, payload: Mapping[str, object], *, first_user_is_admin: bool = True) -> dict[str, object]:
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        display_name = str(payload.get("display_name") or username).strip()
        department_code = validate_department_code(payload.get("department_code"))
        if not username or not password or not department_code:
            raise ValueError("username, password and department_code are required")

        role_code = str(payload.get("role_code") or "").strip()
        if first_user_is_admin and not self.has_users():
            role_code = "super_admin"
        if not role_code:
            role_code = DEFAULT_ROLE_BY_DEPARTMENT.get(department_code, "operation_user")

        record = {
            "username": username,
            "password_hash": hash_password_md5(password),
            "display_name": display_name,
            "department_code": department_code,
            "role_code": role_code,
            "status": str(payload.get("status") or "active"),
        }

        with self.engine.begin() as connection:
            row = connection.execute(insert(AUTH_USER_TABLE).values(**record).returning(AUTH_USER_TABLE)).mappings().one()
        return self._user_with_permissions(dict(row))

    def authenticate(self, username: str, password: str) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                select(AUTH_USER_TABLE).where(AUTH_USER_TABLE.c.username == username.strip())
            ).mappings().first()
            if row is None:
                return None
            item = dict(row)
            if item.get("status") != "active":
                return None
            if item.get("password_hash") != hash_password_md5(password):
                return None
            connection.execute(
                update(AUTH_USER_TABLE)
                .where(AUTH_USER_TABLE.c.id == item["id"])
                .values(last_login_at=datetime.now(timezone.utc))
            )
        return self._user_with_permissions(item)

    def create_session(self, user_id: int, *, ip_address: str | None = None, user_agent: str | None = None) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE_SECONDS)
        with self.engine.begin() as connection:
            connection.execute(
                insert(AUTH_SESSION_TABLE).values(
                    user_id=user_id,
                    token_hash=hash_session_token(token),
                    expires_at=expires_at,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
        return token, expires_at

    def get_user_by_session(self, token: str | None) -> dict[str, object] | None:
        if not token:
            return None
        now = datetime.now(timezone.utc)
        token_hash = hash_session_token(token)
        with self.engine.begin() as connection:
            session = connection.execute(
                select(AUTH_SESSION_TABLE)
                .where(
                    and_(
                        AUTH_SESSION_TABLE.c.token_hash == token_hash,
                        AUTH_SESSION_TABLE.c.revoked_at.is_(None),
                        AUTH_SESSION_TABLE.c.expires_at > now,
                    )
                )
            ).mappings().first()
            if session is None:
                return None
            connection.execute(
                update(AUTH_SESSION_TABLE)
                .where(AUTH_SESSION_TABLE.c.id == session["id"])
                .values(last_seen_at=now)
            )
            user = connection.execute(
                select(AUTH_USER_TABLE).where(AUTH_USER_TABLE.c.id == session["user_id"])
            ).mappings().first()
        if user is None or user["status"] != "active":
            return None
        return self._user_with_permissions(dict(user))

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        with self.engine.begin() as connection:
            connection.execute(
                update(AUTH_SESSION_TABLE)
                .where(AUTH_SESSION_TABLE.c.token_hash == hash_session_token(token))
                .values(revoked_at=datetime.now(timezone.utc))
            )

    def list_users(self) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(select(AUTH_USER_TABLE).order_by(AUTH_USER_TABLE.c.id)).mappings()]
        return [self._user_with_permissions(row) for row in rows]

    def update_user(self, user_id: int, payload: Mapping[str, object]) -> dict[str, object] | None:
        values: dict[str, object] = {}
        for key in ("display_name", "department_code", "role_code", "status"):
            if key in payload and payload[key] is not None:
                values[key] = validate_department_code(payload[key]) if key == "department_code" else str(payload[key]).strip()
        password = payload.get("password")
        if password is not None and str(password):
            values["password_hash"] = hash_password_md5(str(password))
        if not values:
            return self.get_user(user_id)
        with self.engine.begin() as connection:
            row = connection.execute(
                update(AUTH_USER_TABLE)
                .where(AUTH_USER_TABLE.c.id == user_id)
                .values(**values)
                .returning(AUTH_USER_TABLE)
            ).mappings().first()
        return None if row is None else self._user_with_permissions(dict(row))

    def get_user(self, user_id: int) -> dict[str, object] | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(AUTH_USER_TABLE).where(AUTH_USER_TABLE.c.id == user_id)).mappings().first()
        return None if row is None else self._user_with_permissions(dict(row))

    def _user_with_permissions(self, user: dict[str, object]) -> dict[str, object]:
        role_code = str(user.get("role_code") or "")
        with self.engine.connect() as connection:
            role = connection.execute(select(AUTH_ROLE_TABLE).where(AUTH_ROLE_TABLE.c.code == role_code)).mappings().first()
            department = connection.execute(
                select(AUTH_DEPARTMENT_TABLE).where(AUTH_DEPARTMENT_TABLE.c.code == user.get("department_code"))
            ).mappings().first()
        role_dict = dict(role) if role else {}
        permissions = _split_permissions(role_dict.get("permissions"))
        return {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "department_code": user["department_code"],
            "department_name": department["name"] if department else user["department_code"],
            "role_code": role_code,
            "role_name": role_dict.get("name") or role_code,
            "status": user["status"],
            "permissions": permissions,
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "last_login_at": user.get("last_login_at"),
        }
