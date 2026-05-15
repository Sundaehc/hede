"""Daily VIP data import. Run: python -m scripts.import_vip_daily"""

from datetime import date
from pathlib import Path

from config import load_config
from storage.vip_repository import VipRepository

BASE_DIR = Path(r"\\192.168.10.58\超级共享\影刀技术开发部共享\唯品会后台\千百度伊伴")


def main() -> None:
    today = date.today().strftime("%m.%d")  # e.g. "05.15"
    data_dir = BASE_DIR / today

    if not data_dir.exists():
        print(f"[SKIP] 目录不存在: {data_dir}")
        return

    cfg = load_config()
    repo = VipRepository(cfg.database_url)
    result = repo.import_all(data_dir)

    if result["success"]:
        print(f"[OK] {today} 导入完成, 共 {result['total_imported']} 条")
    else:
        print(f"[FAIL] {result['message']}")


if __name__ == "__main__":
    main()
