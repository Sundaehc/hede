from __future__ import annotations

import os
from dataclasses import dataclass, field
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
DEFAULT_JST_MONTHLY_ORDER_FILE = DEFAULT_DAILY_SALES_REPORT_ROOT / "聚水潭近3月订单.xlsx"
DEFAULT_JST_FULL_STOCK_FILE = DEFAULT_DAILY_SALES_REPORT_ROOT / "聚水潭库存.xlsx"
DEFAULT_DEWU_ORDER_ROOT = DEFAULT_DAILY_SALES_REPORT_ROOT
DEFAULT_SMILEY_IMAGE_ROOT = Path(
    r"\\192.168.10.229\图片\产品45主图随时更新\45主图\笑脸45度图"
)
DEFAULT_SMILEY_FINE_TABLE_ROOT = Path(
    r"\\Hede\运营组资料\1.补单表\2026年精细表\笑脸分析表"
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
    smiley_fine_table_root: Path | None = DEFAULT_SMILEY_FINE_TABLE_ROOT
    ni_image_root: Path | None = DEFAULT_NI_IMAGE_ROOT
    jst_stock_root: Path | None = None
    vip_data_root: Path | None = None
    yandou_vip_data_root: Path | None = None
    jst_price_root: Path | None = None
    jst_product_profile_root: Path | None = DEFAULT_JST_PRODUCT_PROFILE_ROOT
    fine_table_export_root: Path | None = DEFAULT_FINE_TABLE_EXPORT_ROOT
    aftersale_return_file: Path | None = DEFAULT_AFTERSALE_RETURN_FILE
    daily_sales_report_root: Path | None = DEFAULT_DAILY_SALES_REPORT_ROOT
    jst_monthly_order_file: Path | None = DEFAULT_JST_MONTHLY_ORDER_FILE
    jst_full_stock_file: Path | None = DEFAULT_JST_FULL_STOCK_FILE
    dewu_order_root: Path | None = DEFAULT_DEWU_ORDER_ROOT
    cbanner_mens_group_source: Path | None = DEFAULT_CBANNER_MENS_GROUP_SOURCE
    cbanner_womens_product_detail_source: Path | None = DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE
    eblan_product_detail_source: Path | None = DEFAULT_EBLAN_PRODUCT_DETAIL_SOURCE
    eblan_product_goods_order_source: Path | None = DEFAULT_EBLAN_PRODUCT_GOODS_ORDER_SOURCE
    ucloud_us3_public_key: str | None = None
    ucloud_us3_private_key: str | None = None
    ucloud_us3_bucket: str | None = None
    ucloud_us3_endpoint: str | None = None
    ucloud_us3_image_prefix: str = ""
    ucloud_us3_signed_url_expires: int = 3600
    ucloud_us3_timeout_seconds: int = 60
    ucloud_us3_sync_workers: int = 4
    request_rate_limit_enabled: bool = True
    request_rate_limit_requests: int = 120
    request_rate_limit_window_seconds: int = 60
    request_rate_limit_burst: int = 20
    request_rate_limit_trusted_proxy_ips: tuple[str, ...] = ("127.0.0.1", "::1")
    ark_api_key: str | None = field(default=None, repr=False)
    doubao_provider: str = "ark"
    doubao_base_url: str = ""
    doubao_text_model: str = "doubao-seed-2-1-pro-260915"
    doubao_timeout_seconds: int = 90

    @property
    def frontend_origins(self) -> tuple[str, ...]:
        """Return all configured browser origins while preserving the legacy env name."""
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in self.frontend_origin.split(",")
            if origin.strip()
        )
        return origins or (DEFAULT_FRONTEND_ORIGIN,)

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

    @property
    def ucloud_us3_configured(self) -> bool:
        return all(
            (
                self.ucloud_us3_public_key,
                self.ucloud_us3_private_key,
                self.ucloud_us3_bucket,
                self.ucloud_us3_endpoint,
            )
        )


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


def _csv_from_env(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


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
    jst_monthly_order_file_raw = os.getenv("JST_MONTHLY_ORDER_FILE")
    jst_monthly_order_file = (
        Path(jst_monthly_order_file_raw)
        if jst_monthly_order_file_raw
        else daily_sales_report_root / "聚水潭近3月订单.xlsx"
    )
    jst_full_stock_file_raw = os.getenv("JST_FULL_STOCK_FILE")
    jst_full_stock_file = (
        Path(jst_full_stock_file_raw)
        if jst_full_stock_file_raw
        else DEFAULT_JST_FULL_STOCK_FILE
    )
    dewu_order_root_raw = os.getenv("DEWU_ORDER_ROOT")
    dewu_order_root = (
        Path(dewu_order_root_raw)
        if dewu_order_root_raw
        else DEFAULT_DEWU_ORDER_ROOT
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
        smiley_fine_table_root=_path_from_env_with_default(
            "SMILEY_FINE_TABLE_ROOT", DEFAULT_SMILEY_FINE_TABLE_ROOT
        ),
        ni_image_root=_path_from_env_with_default("NI_IMAGE_ROOT", DEFAULT_NI_IMAGE_ROOT),
        jst_stock_root=jst_stock_root,
        vip_data_root=vip_data_root,
        yandou_vip_data_root=yandou_vip_data_root,
        jst_price_root=jst_price_root,
        jst_product_profile_root=jst_product_profile_root,
        fine_table_export_root=fine_table_export_root,
        aftersale_return_file=aftersale_return_file,
        daily_sales_report_root=daily_sales_report_root,
        jst_monthly_order_file=jst_monthly_order_file,
        jst_full_stock_file=jst_full_stock_file,
        dewu_order_root=dewu_order_root,
        cbanner_mens_group_source=cbanner_mens_group_source,
        cbanner_womens_product_detail_source=cbanner_womens_product_detail_source,
        eblan_product_detail_source=eblan_product_detail_source,
        eblan_product_goods_order_source=eblan_product_goods_order_source,
        ucloud_us3_public_key=os.getenv("UCLOUD_US3_PUBLIC_KEY") or None,
        ucloud_us3_private_key=os.getenv("UCLOUD_US3_PRIVATE_KEY") or None,
        ucloud_us3_bucket=os.getenv("UCLOUD_US3_BUCKET") or None,
        ucloud_us3_endpoint=os.getenv("UCLOUD_US3_ENDPOINT") or None,
        ucloud_us3_image_prefix=os.getenv("UCLOUD_US3_IMAGE_PREFIX", "").strip().strip("/"),
        ucloud_us3_signed_url_expires=_int_from_env(
            "UCLOUD_US3_SIGNED_URL_EXPIRES", 3600, minimum=60, maximum=86_400
        ),
        ucloud_us3_timeout_seconds=_int_from_env(
            "UCLOUD_US3_TIMEOUT_SECONDS", 60, minimum=5, maximum=300
        ),
        ucloud_us3_sync_workers=_int_from_env(
            "UCLOUD_US3_SYNC_WORKERS", 4, minimum=1, maximum=16
        ),
        request_rate_limit_enabled=_bool_from_env("REQUEST_RATE_LIMIT_ENABLED", True),
        ark_api_key=os.getenv("ARK_API_KEY", "").strip() or None,
        doubao_provider=os.getenv("DOUBAO_PROVIDER", "ark").strip().lower() or "ark",
        doubao_base_url=os.getenv("DOUBAO_BASE_URL", "").strip(),
        doubao_text_model=os.getenv("DOUBAO_TEXT_MODEL", "doubao-seed-2-1-pro-260915").strip() or "doubao-seed-2-1-pro-260915",
        doubao_timeout_seconds=_int_from_env("DOUBAO_TIMEOUT_SECONDS", 90, minimum=10, maximum=300),
        request_rate_limit_requests=_int_from_env(
            "REQUEST_RATE_LIMIT_REQUESTS", 120, minimum=1, maximum=100_000
        ),
        request_rate_limit_window_seconds=_int_from_env(
            "REQUEST_RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1, maximum=86_400
        ),
        request_rate_limit_burst=_int_from_env(
            "REQUEST_RATE_LIMIT_BURST", 20, minimum=0, maximum=100_000
        ),
        request_rate_limit_trusted_proxy_ips=_csv_from_env(
            "REQUEST_RATE_LIMIT_TRUSTED_PROXY_IPS", ("127.0.0.1", "::1")
        ),
    )
