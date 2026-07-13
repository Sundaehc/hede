from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, MetaData, Table, Text, UniqueConstraint, func


METADATA = MetaData()


AUTH_DEPARTMENT_TABLE = Table(
    "auth_departments",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("code", name="uq_auth_departments_code"),
)


AUTH_ROLE_TABLE = Table(
    "auth_roles",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column(
        "department_code",
        Text,
        ForeignKey("auth_departments.code", name="fk_auth_roles_department_code", onupdate="CASCADE"),
        nullable=True,
    ),
    Column("description", Text, nullable=True),
    Column("permissions", Text, nullable=False, default=""),
    Column("is_system", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("code", name="uq_auth_roles_code"),
)


AUTH_USER_TABLE = Table(
    "auth_users",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("username", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column(
        "department_code",
        Text,
        ForeignKey("auth_departments.code", name="fk_auth_users_department_code", onupdate="CASCADE"),
        nullable=False,
    ),
    Column(
        "role_code",
        Text,
        ForeignKey("auth_roles.code", name="fk_auth_users_role_code", onupdate="CASCADE"),
        nullable=False,
    ),
    Column("status", Text, nullable=False, default="active"),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    UniqueConstraint("username", name="uq_auth_users_username"),
)


AUTH_SESSION_TABLE = Table(
    "auth_sessions",
    METADATA,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("auth_users.id", name="fk_auth_sessions_user_id", ondelete="CASCADE"), nullable=False),
    Column("token_hash", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("ip_address", Text, nullable=True),
    Column("user_agent", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
)


Index("idx_auth_sessions_user_id", AUTH_SESSION_TABLE.c.user_id)
Index("idx_auth_sessions_expires_at", AUTH_SESSION_TABLE.c.expires_at)
Index("idx_auth_users_department", AUTH_USER_TABLE.c.department_code)
Index("idx_auth_users_role", AUTH_USER_TABLE.c.role_code)
