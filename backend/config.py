from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE_NAME = ".env"
BACKEND_ROOT = Path(__file__).resolve().parent
DEFAULT_FRONTEND_ORIGIN = "http://127.0.0.1:3001"
DEFAULT_CBANNER_MENS_GROUP_SOURCE = Path(
    r"\\192.168.10.229\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\千百度男鞋"
)
DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE = Path(
    r"\\Hede\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\千百度女鞋"
)
DEFAULT_EBLAN_PRODUCT_DETAIL_SOURCE = Path(
    r"\\Hede\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\伊伴\2026\2026-06"
)
DEFAULT_EBLAN_PRODUCT_GOODS_ORDER_SOURCE = Path(
    r"\\192.168.10.229\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\伊伴\2026\2026-07"
)
DEFAULT_JST_PRODUCT_PROFILE_ROOT = Path(
    r"\\192.168.10.229\商品组-财务组资料\聚水潭商品资料表"
)
DEFAULT_FINE_TABLE_EXPORT_ROOT = Path(
    r"\\192.168.10.229\运营组资料\精细表"
)
DEFAULT_AFTERSALE_RETURN_FILE = Path(
    r"\\192.168.10.229\运营组资料\影刀\商品库存\售后（退货退款）.xlsx"
)
DEFAULT_DAILY_SALES_REPORT_ROOT = Path(
    r"\\Hede\运营组资料\影刀\商品库存"
)
DEFAULT_JST_FULL_STOCK_FILE = DEFAULT_DAILY_SALES_REPORT_ROOT / "聚水潭库存.xlsx"
DEFAULT_SMILEY_IMAGE_ROOT = Path(
    r"\\192.168.10.229\图片\产品45主图随时更新\45主图\笑脸45度图"
)
DEFAULT_NI_IMAGE_ROOT = Path(
    r"\\192.168.10.229\图片\产品45主图随时更新\45主图\NI图片"
)


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    frontend_origin: str
    excel_root: Path
    cbanner_image_root: Path
    yandou_image_root: Path
    eblan_image_root: Path
    smiley_image_root: Path | None = DEFAULT_SMILEY_IMAGE_ROOT
    ni_image_root: Path | None = DEFAULT_NI_IMAGE_ROOT
    jst_stock_root: Path | None = None
    vip_data_root: Path | None = None
    yandou_vip_data_root: Path | None = None
    jst_price_root: Path | None = None
    jst_product_profile_root: Path | None = DEFAULT_JST_PRODUCT_PROFILE_ROOT
    fine_table_export_root: Path | None = DEFAULT_FINE_TABLE_EXPORT_ROOT
    aftersale_return_file: Path | None = DEFAULT_AFTERSALE_RETURN_FILE
    daily_sales_report_root: Path | None = DEFAULT_DAILY_SALES_REPORT_ROOT
    jst_full_stock_file: Path | None = DEFAULT_JST_FULL_STOCK_FILE
    cbanner_mens_group_source: Path | None = DEFAULT_CBANNER_MENS_GROUP_SOURCE
    cbanner_womens_product_detail_source: Path | None = DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE
    eblan_product_detail_source: Path | None = DEFAULT_EBLAN_PRODUCT_DETAIL_SOURCE
    eblan_product_goods_order_source: Path | None = DEFAULT_EBLAN_PRODUCT_GOODS_ORDER_SOURCE
    ai_sql_enabled: bool = False
    ai_api_key: str | None = None
    ai_provider: str = "openai"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    ai_sql_planner_model: str | None = None
    ai_timeout_seconds: int = 180
    ai_sql_max_rows: int = 500
    ai_sql_preflight_enabled: bool = True
    ai_sql_explain_timeout_seconds: int = 5
    ai_sql_max_plan_cost: int = 2_000_000
    ai_sql_max_plan_rows: int = 10_000_000

    @property
    def image_roots(self) -> dict[str, Path]:
        roots = {
            "cbanner": self.cbanner_image_root,
            "yandou": self.yandou_image_root,
            "eblan": self.eblan_image_root,
        }
        if self.smiley_image_root is not None:
            roots["smiley"] = self.smiley_image_root
        if self.ni_image_root is not None:
            roots["ni"] = self.ni_image_root
        return roots

    @property
    def vip_data_roots(self) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()
        for root in (self.vip_data_root, self.yandou_vip_data_root):
            if root is None:
                continue
            key = str(root).rstrip("\\/")
            if key in seen:
                continue
            seen.add(key)
            roots.append(root)
        return roots


def _path_from_env(name: str) -> Path:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required in .env")
    return Path(value)


def _path_from_env_with_default(name: str, default: Path | None) -> Path:
    value = os.getenv(name)
    if not value:
        if default is None:
            raise ValueError(f"{name} is required in .env")
        return default
    return Path(value)


def _bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_from_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(parsed, maximum))


def load_settings(require_database: bool = True) -> Settings:
    load_dotenv(dotenv_path=BACKEND_ROOT / ENV_FILE_NAME, override=False)

    database_url = os.getenv("DATABASE_URL")
    if require_database and not database_url:
        raise ValueError("DATABASE_URL is required in .env")

    jst_stock_root_raw = os.getenv("JST_STOCK_ROOT")
    jst_stock_root = Path(jst_stock_root_raw) if jst_stock_root_raw else None
    vip_data_root_raw = os.getenv("VIP_DATA_ROOT")
    vip_data_root = Path(vip_data_root_raw) if vip_data_root_raw else None
    yandou_vip_data_root_raw = os.getenv("YANDOU_VIP_DATA_ROOT")
    yandou_vip_data_root = Path(yandou_vip_data_root_raw) if yandou_vip_data_root_raw else None
    jst_price_root_raw = os.getenv("JST_PRICE_ROOT")
    jst_price_root = Path(jst_price_root_raw) if jst_price_root_raw else None
    jst_product_profile_root_raw = os.getenv("JST_PRODUCT_PROFILE_ROOT")
    jst_product_profile_root = (
        Path(jst_product_profile_root_raw)
        if jst_product_profile_root_raw
        else DEFAULT_JST_PRODUCT_PROFILE_ROOT
    )
    fine_table_export_root_raw = os.getenv("FINE_TABLE_EXPORT_ROOT")
    fine_table_export_root = (
        Path(fine_table_export_root_raw)
        if fine_table_export_root_raw
        else DEFAULT_FINE_TABLE_EXPORT_ROOT
    )
    aftersale_return_file_raw = os.getenv("AFTERSALE_RETURN_FILE")
    aftersale_return_file = (
        Path(aftersale_return_file_raw)
        if aftersale_return_file_raw
        else DEFAULT_AFTERSALE_RETURN_FILE
    )
    daily_sales_report_root_raw = os.getenv("DAILY_SALES_REPORT_ROOT")
    daily_sales_report_root = (
        Path(daily_sales_report_root_raw)
        if daily_sales_report_root_raw
        else DEFAULT_DAILY_SALES_REPORT_ROOT
    )
    jst_full_stock_file_raw = os.getenv("JST_FULL_STOCK_FILE")
    jst_full_stock_file = (
        Path(jst_full_stock_file_raw)
        if jst_full_stock_file_raw
        else DEFAULT_JST_FULL_STOCK_FILE
    )
    cbanner_mens_group_source_raw = os.getenv("CBANNER_MENS_GROUP_SOURCE")
    cbanner_mens_group_source = (
        Path(cbanner_mens_group_source_raw)
        if cbanner_mens_group_source_raw
        else DEFAULT_CBANNER_MENS_GROUP_SOURCE
    )
    cbanner_womens_product_detail_source_raw = os.getenv("CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE")
    cbanner_womens_product_detail_source = (
        Path(cbanner_womens_product_detail_source_raw)
        if cbanner_womens_product_detail_source_raw
        else DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE
    )
    eblan_product_detail_source_raw = os.getenv("EBLAN_PRODUCT_DETAIL_SOURCE")
    eblan_product_detail_source = (
        Path(eblan_product_detail_source_raw)
        if eblan_product_detail_source_raw
        else DEFAULT_EBLAN_PRODUCT_DETAIL_SOURCE
    )
    eblan_product_goods_order_source_raw = os.getenv("EBLAN_PRODUCT_GOODS_ORDER_SOURCE")
    eblan_product_goods_order_source = (
        Path(eblan_product_goods_order_source_raw)
        if eblan_product_goods_order_source_raw
        else DEFAULT_EBLAN_PRODUCT_GOODS_ORDER_SOURCE
    )

    return Settings(
        database_url=database_url,
        frontend_origin=os.getenv("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),
        excel_root=_path_from_env("EXCEL_ROOT"),
        cbanner_image_root=_path_from_env("CBANNER_IMAGE_ROOT"),
        yandou_image_root=_path_from_env("YANDOU_IMAGE_ROOT"),
        eblan_image_root=_path_from_env("EBLAN_IMAGE_ROOT"),
        smiley_image_root=_path_from_env_with_default("SMILEY_IMAGE_ROOT", DEFAULT_SMILEY_IMAGE_ROOT),
        ni_image_root=_path_from_env_with_default("NI_IMAGE_ROOT", DEFAULT_NI_IMAGE_ROOT),
        jst_stock_root=jst_stock_root,
        vip_data_root=vip_data_root,
        yandou_vip_data_root=yandou_vip_data_root,
        jst_price_root=jst_price_root,
        jst_product_profile_root=jst_product_profile_root,
        fine_table_export_root=fine_table_export_root,
        aftersale_return_file=aftersale_return_file,
        daily_sales_report_root=daily_sales_report_root,
        jst_full_stock_file=jst_full_stock_file,
        cbanner_mens_group_source=cbanner_mens_group_source,
        cbanner_womens_product_detail_source=cbanner_womens_product_detail_source,
        eblan_product_detail_source=eblan_product_detail_source,
        eblan_product_goods_order_source=eblan_product_goods_order_source,
        ai_sql_enabled=_bool_from_env(
            "AI_SQL_ENABLED",
            default=bool(os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")),
        ),
        ai_api_key=os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or None,
        ai_provider=os.getenv("AI_PROVIDER", "openai").strip().lower() or "openai",
        ai_base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
        ai_model=os.getenv("AI_MODEL", "gpt-4.1-mini"),
        ai_sql_planner_model=(
            os.getenv("AI_SQL_PLANNER_MODEL", "").strip() or None
        ),
        ai_timeout_seconds=_int_from_env(
            "AI_TIMEOUT_SECONDS", 180, minimum=5, maximum=300
        ),
        ai_sql_max_rows=_int_from_env(
            "AI_SQL_MAX_ROWS", 500, minimum=1, maximum=2000
        ),
        ai_sql_preflight_enabled=_bool_from_env(
            "AI_SQL_PREFLIGHT_ENABLED", True
        ),
        ai_sql_explain_timeout_seconds=_int_from_env(
            "AI_SQL_EXPLAIN_TIMEOUT_SECONDS", 5, minimum=1, maximum=30
        ),
        ai_sql_max_plan_cost=_int_from_env(
            "AI_SQL_MAX_PLAN_COST", 2_000_000, minimum=10_000, maximum=100_000_000
        ),
        ai_sql_max_plan_rows=_int_from_env(
            "AI_SQL_MAX_PLAN_ROWS", 10_000_000, minimum=100_000, maximum=1_000_000_000
        ),
    )
