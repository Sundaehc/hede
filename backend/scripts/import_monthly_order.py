"""Daily monthly JST order import (8:00). Run: python -m scripts.import_monthly_order"""

from datetime import date
from pathlib import Path

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> None:
    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.jst_stock_root is not None, "JST_STOCK_ROOT is required in .env"

    repo = VipRepository(cfg.database_url)

    other_platform_dir = cfg.jst_stock_root.parent / "其他平台" / date.today().strftime("%m.%d")
    file_path = other_platform_dir / "月聚水潭.xlsx"

    if file_path.exists():
        result = repo.import_monthly_order(file_path)
        print(f"[JST月订单] {date.today().strftime('%m.%d')} 导入完成, 共 {result['imported']} 条")
    else:
        print(f"[SKIP] 月聚水潭文件不存在: {file_path}")


if __name__ == "__main__":
    main()
