from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy import text


def allowed_profiles(user):
    permissions = {value.strip() for value in (user.get("permissions") or "").split(",")}
    if user.get("status") != "active" or not permissions.intersection({"*", "product.view"}):
        return []
    profiles = ["products"]
    if user.get("role_code") == "super_admin" or user.get("department_code") == "美工部":
        profiles.append("design")
    return profiles


def issue_credential(connection, *, profile, days, label, user_id=None, username=None):
    label = label.strip()
    if profile not in {"products", "design"} or (days is not None and (type(days) is not int or not 1 <= days <= 90)) or not 1 <= len(label) <= 100:
        raise ValueError("profile、有效期或标签不正确（1至90天或永久有效）")
    condition = "users.id=:identity" if user_id is not None else "users.username=:identity"
    lock = " FOR SHARE OF users, roles" if connection.dialect.name == "postgresql" else ""
    user = connection.execute(text(f"""SELECT users.id,users.username,users.display_name,users.status,
        users.department_code,users.role_code,roles.permissions
        FROM public.auth_users users JOIN public.auth_roles roles ON roles.code=users.role_code
        WHERE {condition}{lock}"""), {"identity": user_id if user_id is not None else username}).mappings().first()
    if user is None or "products" not in allowed_profiles(user):
        raise ValueError("用户不存在、已停用或无商品查看权限")
    if profile not in allowed_profiles(user):
        raise ValueError("文案查询仅允许美工部或超级管理员")
    if days is None and connection.dialect.name == "postgresql":
        if connection.scalar(text("""SELECT attnotnull FROM pg_attribute
            WHERE attrelid='mcp_private.tokens'::regclass AND attname='expires_at' AND NOT attisdropped""")):
            raise ValueError("永久有效尚未启用，请管理员执行 upgrade-token-expiry --execute 并更新重启独立MCP服务")
    token = "hmcp_" + secrets.token_urlsafe(32)
    expires_at = None if days is None else datetime.now(timezone.utc) + timedelta(days=days)
    item = dict(connection.execute(text("""INSERT INTO mcp_private.tokens
        (user_id,token_hash,label,profile,expires_at) VALUES (:user_id,:token_hash,:label,:profile,:expires_at)
        RETURNING id,user_id,label,profile,expires_at,revoked_at,created_at"""), {
            "user_id": user["id"], "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "label": label, "profile": profile, "expires_at": expires_at,
        }).mappings().one())
    item.update(username=user["username"], display_name=user["display_name"], department_code=user["department_code"], state="active")
    return {"token": token, "item": item}


def credential_state(row):
    if row["revoked_at"] is not None:
        return "revoked"
    expires_at = row["expires_at"]
    if expires_at is not None:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return "expired"
    if row["profile"] not in allowed_profiles(row):
        return "blocked"
    return "active"


def list_credentials(connection, *, page, page_size):
    total = connection.scalar(text("SELECT count(*) FROM mcp_private.tokens"))
    rows = connection.execute(text("""SELECT token.id,token.user_id,token.label,token.profile,
        token.expires_at,token.revoked_at,token.created_at,users.username,users.display_name,
        users.department_code,users.status,users.role_code,roles.permissions
        FROM mcp_private.tokens token JOIN public.auth_users users ON users.id=token.user_id
        JOIN public.auth_roles roles ON roles.code=users.role_code
        ORDER BY token.id DESC LIMIT :limit OFFSET :offset"""), {
            "limit": page_size, "offset": (page - 1) * page_size,
        }).mappings()
    items = []
    for row in rows:
        item = dict(row)
        item["state"] = credential_state(row)
        for field in ("status", "role_code", "permissions"):
            item.pop(field)
        items.append(item)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def list_candidates(connection, *, query, page):
    pattern = "%" + query.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    conditions = """users.status='active' AND (lower(users.username) LIKE :pattern ESCAPE '!'
        OR lower(users.display_name) LIKE :pattern ESCAPE '!')
        AND ((',' || replace(COALESCE(roles.permissions,''),' ','') || ',') LIKE '%,product.view,%'
        OR (',' || replace(COALESCE(roles.permissions,''),' ','') || ',') LIKE '%,*,%')"""
    source = "public.auth_users users JOIN public.auth_roles roles ON roles.code=users.role_code"
    parameters = {"pattern": pattern, "offset": (page - 1) * 30}
    total = connection.scalar(text(f"SELECT count(*) FROM {source} WHERE {conditions}"), parameters)
    rows = connection.execute(text(f"""SELECT users.id,users.username,users.display_name,users.department_code,
        users.status,users.role_code,roles.permissions FROM {source} WHERE {conditions}
        ORDER BY users.username,users.id LIMIT 30 OFFSET :offset"""), parameters).mappings()
    items = [{"id": row["id"], "username": row["username"], "display_name": row["display_name"],
        "department_code": row["department_code"], "profiles": allowed_profiles(row)} for row in rows]
    return {"items": items, "total": total, "page": page, "page_size": 30}


def revoke_credential(connection, token_id):
    item = connection.execute(text("""UPDATE mcp_private.tokens SET revoked_at=CURRENT_TIMESTAMP
        WHERE id=:id AND revoked_at IS NULL RETURNING id,user_id,label,profile,revoked_at"""), {"id": token_id}).mappings().first()
    if item is not None:
        return dict(item), True
    item = connection.execute(text("SELECT id,user_id,label,profile,revoked_at FROM mcp_private.tokens WHERE id=:id"), {"id": token_id}).mappings().first()
    return (dict(item) if item is not None else None), False
