from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE_NAME = ".env"
BACKEND_ROOT = Path(__file__).resolve().parent
DEFAULT_FRONTEND_ORIGIN = "http://127.0.0.1:3000"
DEFAULT_CBANNER_MENS_GROUP_SOURCE = Path(
    r"\\192.168.10.229\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\千百度男鞋"
)
DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE = Path(
    r"\\Hede\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\千百度女鞋"
)
DEFAULT_EBLAN_PRODUCT_DETAIL_SOURCE = Path(
    r"\\Hede\运营组资料\9商品组（卢嘉诚）\商品分析\商品运营货品表\伊伴\2026\2026-06"
)


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    frontend_origin: str
    excel_root: Path
    cbanner_image_root: Path
    yandou_image_root: Path
    eblan_image_root: Path
    jst_stock_root: Path | None = None
    vip_data_root: Path | None = None
    yandou_vip_data_root: Path | None = None
    jst_price_root: Path | None = None
    cbanner_mens_group_source: Path | None = DEFAULT_CBANNER_MENS_GROUP_SOURCE
    cbanner_womens_product_detail_source: Path | None = DEFAULT_CBANNER_WOMENS_PRODUCT_DETAIL_SOURCE
    eblan_product_detail_source: Path | None = DEFAULT_EBLAN_PRODUCT_DETAIL_SOURCE

    @property
    def image_roots(self) -> dict[str, Path]:
        return {
            "cbanner": self.cbanner_image_root,
            "yandou": self.yandou_image_root,
            "eblan": self.eblan_image_root,
        }

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

    return Settings(
        database_url=database_url,
        frontend_origin=os.getenv("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),
        excel_root=_path_from_env("EXCEL_ROOT"),
        cbanner_image_root=_path_from_env("CBANNER_IMAGE_ROOT"),
        yandou_image_root=_path_from_env("YANDOU_IMAGE_ROOT"),
        eblan_image_root=_path_from_env("EBLAN_IMAGE_ROOT"),
        jst_stock_root=jst_stock_root,
        vip_data_root=vip_data_root,
        yandou_vip_data_root=yandou_vip_data_root,
        jst_price_root=jst_price_root,
        cbanner_mens_group_source=cbanner_mens_group_source,
        cbanner_womens_product_detail_source=cbanner_womens_product_detail_source,
        eblan_product_detail_source=eblan_product_detail_source,
    )
