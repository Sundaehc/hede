"""Daily VIP data import (12:00). Run: python -m scripts.import_vip_daily"""

from datetime import date

from config import load_settings
from storage.vip_repository import VipRepository


def main() -> None:
    cfg = load_settings()
    assert cfg.database_url is not None
    assert cfg.vip_data_roots, "VIP_DATA_ROOT or YANDOU_VIP_DATA_ROOT is required in .env"
    repo = VipRepository(cfg.database_url)

    replace_existing = True
    total_imported = 0
    missing_directories: list[str] = []
    failed_imports: list[str] = []
    for root in cfg.vip_data_roots:
        vip_dir = root / date.today().strftime("%m.%d")
        if not vip_dir.exists():
            print(f"[SKIP] VIP 目录不存在: {vip_dir}")
            missing_directories.append(str(vip_dir))
            continue

        result = repo.import_all(vip_dir, replace_existing=replace_existing)
        if result["success"]:
            replace_existing = False
            total_imported += int(result["total_imported"])
            print(f"[VIP] {vip_dir} 导入完成, 共 {result['total_imported']} 条")
        else:
            print(f"[VIP] {result['message']}")
            failed_imports.append(f"{vip_dir}: {result['message']}")

    if missing_directories or failed_imports:
        details = [*missing_directories, *failed_imports]
        raise SystemExit(f"[VIP] {date.today().strftime('%m.%d')} 导入不完整: {'; '.join(details)}")

    print(f"[VIP] {date.today().strftime('%m.%d')} 全部导入完成, 共 {total_imported} 条")


if __name__ == "__main__":
    main()
