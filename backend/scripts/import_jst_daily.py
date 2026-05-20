"""Daily JST size stock and purchase diff import (8:00). Run: python -m scripts.import_jst_daily"""

from datetime import date

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> None:
    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.jst_stock_root is not None, "JST_STOCK_ROOT is required in .env"

    repo = VipRepository(cfg.database_url)
    today_dir = cfg.jst_stock_root / date.today().strftime("%m.%d")

    # 尺码表
    size_file = today_dir / "商品库存.xlsx"
    if size_file.exists():
        result = repo.import_size_stock(size_file)
        print(f"[尺码表] 导入完成, 共 {result['imported']} 条")
    else:
        print(f"[SKIP] 商品库存不存在: {size_file}")

    # 采购差异
    diff_file = today_dir / "采购单管理.xlsx"
    if diff_file.exists():
        result = repo.import_purchase_diff(diff_file)
        print(f"[采购差异] 导入完成, 共 {result['imported']} 条")
    else:
        print(f"[SKIP] 采购单管理不存在: {diff_file}")


if __name__ == "__main__":
    main()
