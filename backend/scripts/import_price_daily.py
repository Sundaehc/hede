"""Daily price data import (14:00). Run: python -m scripts.import_price_daily"""

from datetime import date

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> None:
    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.jst_price_root is not None, "JST_PRICE_ROOT is required in .env"
    repo = VipRepository(cfg.database_url)

    price_dir = cfg.jst_price_root / date.today().strftime("%Y-%m-%d")
    if price_dir.exists():
        result = repo.import_all(price_dir)
        if result["success"]:
            print(f"[PRICE] {result['batch_date']} 导入完成, 共 {result['total_imported']} 条")
        else:
            print(f"[PRICE] {result['message']}")
    else:
        print(f"[SKIP] 物价目录不存在: {price_dir}")


if __name__ == "__main__":
    main()
