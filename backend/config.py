from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE_NAME = ".env"
BACKEND_ROOT = Path(__file__).resolve().parent

DEFAULT_EXCEL_ROOT = Path(r"\\192.168.10.229\运营组资料\9商品组（卢嘉诚）\商品档案\商品基础信息\商品资料档案汇总")
DEFAULT_QBD_IMAGE_ROOT = Path(r"\\192.168.10.229\图片\产品45主图随时更新\45主图\千百度45度图男女鞋")
DEFAULT_YANDOU_IMAGE_ROOT = Path(r"\\192.168.10.229\图片\产品45主图随时更新\45主图\烟斗45图准确版")
DEFAULT_YIBAN_IMAGE_ROOT = Path(r"\\192.168.10.229\图片\产品45主图随时更新\45主图\伊伴男女鞋45度图")
DEFAULT_FRONTEND_ORIGIN = "http://192.168.10.80:3000"


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    frontend_origin: str
    excel_root: Path
    qbd_image_root: Path
    yandou_image_root: Path
    yiban_image_root: Path

    @property
    def image_roots(self) -> dict[str, Path]:
        return {
            "qbd": self.qbd_image_root,
            "yandou": self.yandou_image_root,
            "yiban": self.yiban_image_root,
        }


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    return Path(value)


def load_settings(require_database: bool = True) -> Settings:
    load_dotenv(dotenv_path=BACKEND_ROOT / ENV_FILE_NAME, override=False)

    database_url = os.getenv("DATABASE_URL")
    if require_database and not database_url:
        raise ValueError("DATABASE_URL is required in .env")

    return Settings(
        database_url=database_url,
        frontend_origin=os.getenv("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN),
        excel_root=_path_from_env("EXCEL_SOURCE_ROOT", DEFAULT_EXCEL_ROOT),
        qbd_image_root=_path_from_env("QBD_IMAGE_ROOT", DEFAULT_QBD_IMAGE_ROOT),
        yandou_image_root=_path_from_env("YANDOU_IMAGE_ROOT", DEFAULT_YANDOU_IMAGE_ROOT),
        yiban_image_root=_path_from_env("YIBAN_IMAGE_ROOT", DEFAULT_YIBAN_IMAGE_ROOT),
    )
