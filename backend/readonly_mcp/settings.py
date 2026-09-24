from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MCPSettings:
    products_url: str = field(repr=False)
    design_url: str = field(repr=False)
    control_url: str = field(repr=False)
    port: int = 8765
    allowed_hosts: tuple[str, ...] = ("127.0.0.1:8765", "localhost:8765")
    allowed_origins: tuple[str, ...] = ()
    max_rows: int = 200
    timeout_ms: int = 10000
    max_bytes: int = 512000
    department_urls: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls):
        load_dotenv(BACKEND_ROOT / ".env", override=False)
        urls = [os.getenv(name, "") for name in ("MCP_PRODUCTS_DATABASE_URL", "MCP_DESIGN_DATABASE_URL", "MCP_CONTROL_DATABASE_URL")]
        if not all(urls):
            raise ValueError("缺少MCP专用数据库账号配置，请先执行setup；不能使用业务管理员账号代替")
        parsed = [make_url(url) for url in urls]
        if any(url.drivername != "postgresql+psycopg" for url in parsed):
            raise ValueError("MCP只支持postgresql+psycopg连接")
        if len({(url.host, url.port, url.database) for url in parsed}) != 1:
            raise ValueError("三个MCP专用账号必须连接同一数据库")
        port = int(os.getenv("MCP_PORT", "8765"))
        hosts = tuple(value.strip() for value in os.getenv("MCP_ALLOWED_HOSTS", f"127.0.0.1:{port},localhost:{port}").split(",") if value.strip())
        origins = tuple(value.strip() for value in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",") if value.strip())
        if not 1024 <= port <= 65535 or not hosts or any("*" in value for value in (*hosts, *origins)):
            raise ValueError("MCP端口或Host/Origin白名单不正确；不允许通配符")
        from readonly_mcp.catalog import PROFILE_PERMISSIONS
        department_urls = {profile: os.getenv(f"MCP_{profile.upper()}_DATABASE_URL", "") for profile in PROFILE_PERMISSIONS}
        if any(department_urls.values()) and not all(department_urls.values()):
            raise ValueError("部门MCP数据库连接配置不完整")
        if department_urls and all(department_urls.values()):
            if any(make_url(value).drivername != "postgresql+psycopg" or
                   (make_url(value).host, make_url(value).port, make_url(value).database) !=
                   (parsed[0].host, parsed[0].port, parsed[0].database)
                   for value in department_urls.values()):
                raise ValueError("部门MCP数据库账号必须使用同一PostgreSQL库")
        else:
            department_urls = {}
        return cls(*urls, port=port, allowed_hosts=hosts, allowed_origins=origins, department_urls=department_urls)
