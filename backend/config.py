from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE_NAME = ".env"
BACKEND_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    frontend_origin: str
    excel_root: Path
    qbd_image_root: Path
    yandou_image_root: Path
    yiban_image_root: Path
    jst_stock_root: Path | None = None

    @property
    def image_roots(self) -> dict[str, Path]:
        return {
            "qbd": self.qbd_image_root,
            "yandou": self.yandou_image_root,
            "yiban": self.yiban_image_root,
        }


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

    return Settings(
        database_url=database_url,
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:3000"),
        excel_root=_path_from_env("EXCEL_ROOT"),
        qbd_image_root=_path_from_env("QBD_IMAGE_ROOT"),
        yandou_image_root=_path_from_env("YANDOU_IMAGE_ROOT"),
        yiban_image_root=_path_from_env("YIBAN_IMAGE_ROOT"),
        jst_stock_root=jst_stock_root,
    )
