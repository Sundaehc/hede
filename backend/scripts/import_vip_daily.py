"""Daily VIP data import (12:00). Run: python -m scripts.import_vip_daily"""

from datetime import date

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> None:
    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.vip_data_root is not None, "VIP_DATA_ROOT is required in .env"
    repo = VipRepository(cfg.database_url)

    vip_dir = cfg.vip_data_root / date.today().strftime("%m.%d")
    if vip_dir.exists():
        result = repo.import_all(vip_dir)
        if result["success"]:
            print(f"[VIP] {result['batch_date']} 导入完成, 共 {result['total_imported']} 条")
        else:
            print(f"[VIP] {result['message']}")
    else:
        print(f"[SKIP] VIP 目录不存在: {vip_dir}")


if __name__ == "__main__":
    main()
