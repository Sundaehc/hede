"""Import 聚水潭商品资料表 files into jst_product_profiles.

Run:
    python -m scripts.import_jst_product_profiles
    python -m scripts.import_jst_product_profiles --source-root "\\\\192.168.10.229\\商品组-财务组资料\\聚水潭商品资料表"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="导入聚水潭商品资料表")
    parser.add_argument("--source-root", type=Path, default=None, help="聚水潭商品资料表目录")
    args = parser.parse_args()

    cfg = load_settings()
    assert cfg.database_url is not None
    source_root = args.source_root or cfg.jst_product_profile_root
    assert source_root is not None, "JST_PRODUCT_PROFILE_ROOT is required in .env"

    repo = VipRepository(cfg.database_url)
    result = repo.import_product_profiles(source_root)
    print(result)
    return 0 if int(result.get("imported") or 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
